"""Licensed real-world footage and photos.

Sources (all allow reuse in monetised videos):
  • Pixabay videos + photos  (Pixabay Content License)
  • Pexels videos + photos   (Pexels License)            — optional, needs PEXELS_API_KEY
  • Wikimedia Commons / Wikipedia lead images, filtered to Public Domain, CC0, CC BY, CC BY-SA
We deliberately do NOT scrape Google Images, news sites or YouTube: that footage is copyrighted and
gets channels Content-ID claims and strikes.
"""
import re, urllib.parse, threading
from concurrent.futures import ThreadPoolExecutor
from .util import CACHE, http, download, sha, run, log, load_json, save_json
from .config import env
from . import history

FREE_LICENSE = re.compile(r'^(public domain|pd|cc0|cc by(-sa)?( \d\.\d)?|cc-by(-sa)?|attribution|no restrictions|cc by 2\.0|cc by-sa \d)', re.I)
VID = CACHE / 'clips'; PHO = CACHE / 'photos'; RAW = CACHE / 'raw'
for d in (VID, PHO, RAW): d.mkdir(parents=True, exist_ok=True)
META = CACHE / 'meta.json'


class Assets:
    def __init__(self, cfg, hist):
        self.cfg, self.hist = cfg, hist
        self.pixabay = env('PIXABAY_API_KEY'); self.pexels = env('PEXELS_API_KEY') if cfg['assets'].get('pexels') else None
        self.meta = load_json(META, {})
        self.used, self.credits = [], {}
        self.lock = threading.RLock()

    # ------------------------------------------------------------- video
    def _pixabay_videos(self, q):
        if not self.pixabay: return []
        r = http('GET', 'https://pixabay.com/api/videos/', params=dict(key=self.pixabay, q=q[:100], per_page=20, safesearch='true'))
        out = []
        for h in r.json().get('hits', []):
            v = h['videos'].get('large') if h['videos'].get('large', {}).get('width', 0) and h['videos']['large']['width'] <= 1920 else None
            v = v or (h['videos']['small'] if h['videos']['small'].get('width', 0) >= 1280 else h['videos'].get('medium'))
            if not v or not v.get('url') or v.get('width', 0) < 960: continue
            out.append(dict(id=f"pixabay:{h['id']}", url=v['url'], w=v['width'], dur=h['duration'], credit=f"{h['pageURL']} by {h['user']}", src='Pixabay'))
        return out

    def _pexels_videos(self, q):
        if not self.pexels: return []
        r = http('GET', 'https://api.pexels.com/videos/search', headers={'Authorization': self.pexels},
                 params=dict(query=q[:100], per_page=15, orientation='landscape'))
        out = []
        for v in r.json().get('videos', []):
            files = sorted([f for f in v['video_files'] if (f.get('width') or 0) >= 1280 and f.get('file_type') == 'video/mp4'],
                           key=lambda f: abs((f.get('width') or 0) - 1920))
            if files:
                out.append(dict(id=f"pexels:{v['id']}", url=files[0]['link'], w=files[0]['width'], dur=v['duration'],
                                credit=f"{v['url']} by {v['user']['name']}", src='Pexels'))
        return out

    def video(self, query):
        key = 'v:' + query.lower().strip()
        if key in self.meta and (VID / self.meta[key]['file']).exists():
            m = self.meta[key]; self._use(m['id'], m['credit']); return VID / m['file']
        cands = []
        for fn in (self._pixabay_videos, self._pexels_videos):
            try: cands += fn(query)
            except Exception as e: log.warning('video search failed (%s): %s', query, e)
        days = self.cfg['assets'].get('reuse_block_days', 21)
        fresh = [c for c in cands if c['dur'] >= 5 and c['id'] not in self.used and not history.asset_recent(self.hist, c['id'], days)]
        pick = (fresh or [c for c in cands if c['id'] not in self.used] or cands or [None])[0]
        if not pick:
            log.warning('no footage for "%s"', query); return None
        raw = RAW / f"{sha(pick['id'])}.mp4"
        out = VID / f"{sha(pick['id'])}.mp4"
        try:
            download(pick['url'], raw)
            if not out.exists():
                run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(raw), '-an', '-t', '11', '-vf',
                     'setpts=1.25*PTS,scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080,fps=30,eq=saturation=0.75:contrast=1.04',
                     '-t', '13.5', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p', str(out)])
            raw.unlink(missing_ok=True)
        except Exception as e:
            log.warning('footage download/grade failed %s: %s', pick['id'], e); return None
        with self.lock:
            self.meta[key] = dict(id=pick['id'], file=out.name, credit=pick['credit'], src=pick['src']); save_json(self.meta, META)
            self._use(pick['id'], pick['credit'])
        return out

    # ------------------------------------------------------------- photos
    def _commons_info(self, titles=None, search=None, n=8):
        p = dict(action='query', format='json', prop='imageinfo', iiprop='url|size|extmetadata|mime', iiurlwidth=1920)
        if titles: p['titles'] = titles
        else: p.update(generator='search', gsrnamespace=6, gsrsearch=f'{search} filetype:bitmap', gsrlimit=n)
        r = http('GET', 'https://commons.wikimedia.org/w/api.php', params=p)
        pages = sorted(r.json().get('query', {}).get('pages', {}).values(), key=lambda x: x.get('index', 0))
        out = []
        for pg in pages:
            ii = (pg.get('imageinfo') or [{}])[0]; m = ii.get('extmetadata', {})
            g = lambda k: re.sub('<[^>]+>', '', m.get(k, {}).get('value', '')).strip()
            lic = g('LicenseShortName') or g('License')
            if not ii.get('url') or 'image/' not in ii.get('mime', 'image/'): continue
            if not FREE_LICENSE.match(lic or ''): continue
            if ii.get('width', 0) < 500: continue
            out.append(dict(id='commons:' + pg['title'], url=ii.get('thumburl') or ii['url'], url2=ii['url'], w=ii.get('width'),
                            credit=f"{pg['title'][5:]} by {g('Artist')[:60] or 'unknown'}, {lic} (Wikimedia Commons)"))
        return out

    def _save_photo(self, key, c):
        out = PHO / f"{sha(c['id'])}.jpg"
        try: download(c['url'], out)
        except Exception:
            if not c.get('url2') or c['url2'] == c['url']: raise
            download(c['url2'], out)          # original file if the resized thumbnail host is unavailable
        with self.lock:
            self.meta[key] = dict(id=c['id'], file=out.name, credit=c['credit']); save_json(self.meta, META)
            self._use(c['id'], c['credit'])
        return out

    def _cached(self, key):
        if key in self.meta and (PHO / self.meta[key]['file']).exists():
            m = self.meta[key]; self._use(m['id'], m['credit']); return PHO / m['file']

    def commons(self, query):
        key = 'c:' + query.lower().strip()
        hit = self._cached(key)
        if hit: return hit
        try:
            for c in self._commons_info(search=query):
                if c['id'] not in self.used: return self._save_photo(key, c)
        except Exception as e: log.warning('commons search failed (%s): %s', query, e)
        return None

    def wiki(self, title):
        """Lead image of a Wikipedia article (people, companies, places) — only if freely licensed."""
        key = 'w:' + title.lower().strip()
        hit = self._cached(key)
        if hit: return hit
        try:
            r = http('GET', 'https://en.wikipedia.org/api/rest_v1/page/summary/' + urllib.parse.quote(title.replace(' ', '_')), ok=(200, 404))
            img = r.json().get('originalimage', {}).get('source') if r.status_code == 200 else None
            if img and '/commons/' in img:
                fname = urllib.parse.unquote(img.split('/')[-1])
                if re.match(r'^\d+px-', fname): fname = fname.split('px-', 1)[1]
                cs = self._commons_info(titles='File:' + fname)
                if cs: return self._save_photo(key, cs[0])
        except Exception as e: log.warning('wiki image failed (%s): %s', title, e)
        return self.commons(title)

    def stock_photo(self, query):
        key = 's:' + query.lower().strip()
        hit = self._cached(key)
        if hit: return hit
        try:
            if self.pixabay:
                r = http('GET', 'https://pixabay.com/api/', params=dict(key=self.pixabay, q=query[:100], image_type='photo', per_page=20, safesearch='true', min_width=1600))
                for h in r.json().get('hits', []):
                    c = dict(id=f"pixabay-img:{h['id']}", url=h['largeImageURL'], credit=f"{h['pageURL']} by {h['user']} (Pixabay)")
                    if c['id'] not in self.used: return self._save_photo(key, c)
            if self.pexels:
                r = http('GET', 'https://api.pexels.com/v1/search', headers={'Authorization': self.pexels}, params=dict(query=query[:100], per_page=15))
                for p in r.json().get('photos', []):
                    c = dict(id=f"pexels-img:{p['id']}", url=p['src']['large2x'], credit=f"{p['url']} by {p['photographer']} (Pexels)")
                    if c['id'] not in self.used: return self._save_photo(key, c)
        except Exception as e: log.warning('stock photo failed (%s): %s', query, e)
        return None

    # ------------------------------------------------------------- resolve a storyboard
    def resolve_bg(self, bg):
        """bg spec -> ('v'|'p', path) or None.  Specs: {"video": q} {"photo": {"wiki"|"commons"|"stock": q}}"""
        if not bg: return None
        if isinstance(bg, str): bg = {'video': bg}
        if bg.get('video'):
            p = self.video(bg['video'])
            if p: return ('v', str(p))
            if bg.get('fallback_photo'): bg = {'photo': {'commons': bg['fallback_photo']}}
            else: return None
        ph = bg.get('photo') or {}
        if isinstance(ph, str): ph = {'commons': ph}
        p = (self.wiki(ph['wiki']) if ph.get('wiki') else self.commons(ph['commons']) if ph.get('commons')
             else self.stock_photo(ph['stock']) if ph.get('stock') else None)
        return ('p', str(p)) if p else None

    def resolve_storyboard(self, sb, workers=3):
        jobs = []
        for si, sec in enumerate(sb['sections']):
            if sec.get('bg'): jobs.append(('sec', si, None, sec['bg']))
            for bi, b in enumerate(sec['beats']):
                if b.get('bg'): jobs.append(('beat', si, bi, b['bg']))
                if b['type'] in ('person', 'quote') and (b.get('wiki') or b.get('photo')):
                    jobs.append(('photo', si, bi, {'photo': {'wiki': b['wiki']}} if b.get('wiki') else {'photo': b['photo']}))
        # serialise per-query to keep cache coherent; parallelise downloads of distinct queries
        uniq = {}
        for j in jobs: uniq.setdefault(repr(j[3]), j[3])
        res = {}
        with ThreadPoolExecutor(workers) as ex:
            for k, v in zip(uniq, ex.map(self._safe_resolve, uniq.values())): res[k] = v
        for kind, si, bi, spec in jobs:
            r = res.get(repr(spec))
            if kind == 'sec': sb['sections'][si]['_bg'] = r
            elif kind == 'beat': sb['sections'][si]['beats'][bi]['_bg'] = r
            elif r:
                b = sb['sections'][si]['beats'][bi]; b['_photo'] = r[1]
                cr = self.credit_for(r[1]); cr = cr.split(' by ', 1)[1] if ' by ' in cr else cr
                b['_credit'] = 'Photo: ' + cr.replace(' (Wikimedia Commons)', '').replace(' (Pixabay)', ' / Pixabay')[:80]
        return sb

    def _safe_resolve(self, spec):
        try: return self.resolve_bg(spec)
        except Exception as e:
            log.warning('asset resolve failed %s: %s', spec, e); return None

    def _use(self, aid, credit):
        with self.lock:
            if aid not in self.used: self.used.append(aid)
            self.credits[aid] = credit

    def credit_for(self, path):
        name = str(path).replace('\\', '/').split('/')[-1]
        for m in self.meta.values():
            if m['file'] == name: return m['credit']
        return ''

    def credit_lines(self):
        photos = [c for i, c in self.credits.items() if i.startswith('commons:')]
        stock = sorted({('Pixabay' if 'pixabay' in i else 'Pexels') for i in self.credits if i.startswith(('pixabay', 'pexels'))})
        out = []
        if photos: out += ['Photos (Wikimedia Commons):'] + [f'- {c}' for c in photos]
        if stock: out += [f"Stock footage/photos: {', '.join(stock)} (free-to-use licenses)."]
        return out
