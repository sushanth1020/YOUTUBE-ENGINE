"""Daily signals: fresh news (Google News RSS) + what's working on YouTube (trending + benchmark-channel outliers)."""
import random, statistics, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from .util import http, log, load_json, save_json, DATA


def google_news(queries, region='IN', per_query=6):
    hl, ceid = ('en-IN', 'IN:en') if region == 'IN' else ('en-US', 'US:en')
    out, seen = [], set()
    for q in queries:
        url = f'https://news.google.com/rss/search?q={urllib.parse.quote(q + " when:2d")}&hl={hl}&gl={region}&ceid={ceid}'
        try:
            root = ET.fromstring(http('GET', url, retries=2).content)
            for it in root.iter('item'):
                t = it.findtext('title') or ''
                if t in seen: continue
                seen.add(t); out.append(dict(q=q, title=t, date=it.findtext('pubDate'), source=(it.find('source').text if it.find('source') is not None else '')))
                if sum(1 for o in out if o['q'] == q) >= per_query: break
        except Exception as e:
            log.warning('news fetch failed for %s: %s', q, e)
    return out


def _iso_dur(s):
    import re
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', s or '')
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0


def youtube_signals(yt, keywords, channels, region='IN'):
    """Trending long-form finance videos from the last 7 days + benchmark channels' recent outliers."""
    out = {'trending': [], 'outliers': []}
    if yt is None: return out
    after = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    ids = []
    for kw in random.sample(keywords, min(3, len(keywords))):
        try:
            r = yt.search().list(part='id', q=kw, type='video', order='viewCount', publishedAfter=after, regionCode=region,
                                 relevanceLanguage='en', videoDuration='medium', maxResults=15).execute()
            ids += [i['id']['videoId'] for i in r.get('items', [])]
        except Exception as e:
            log.warning('youtube search failed: %s', e); break
    if ids:
        try:
            vs = yt.videos().list(part='snippet,statistics,contentDetails', id=','.join(list(dict.fromkeys(ids))[:50])).execute()
            for v in vs.get('items', []):
                out['trending'].append(dict(title=v['snippet']['title'], channel=v['snippet']['channelTitle'],
                                            views=int(v['statistics'].get('viewCount', 0)), minutes=round(_iso_dur(v['contentDetails']['duration']) / 60)))
            out['trending'].sort(key=lambda x: -x['views'])
        except Exception as e: log.warning('youtube videos.list failed: %s', e)
    # benchmark channels: which recent uploads beat that channel's own median?
    cache = load_json(DATA / 'channel_ids.json', {})
    for handle in channels:
        try:
            if handle not in cache:
                r = yt.channels().list(part='contentDetails', forHandle=handle.lstrip('@')).execute()
                if not r.get('items'): continue
                cache[handle] = r['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            pl = yt.playlistItems().list(part='contentDetails', playlistId=cache[handle], maxResults=15).execute()
            vids = [i['contentDetails']['videoId'] for i in pl.get('items', [])]
            vs = yt.videos().list(part='snippet,statistics', id=','.join(vids)).execute().get('items', [])
            views = [int(v['statistics'].get('viewCount', 0)) for v in vs]
            if len(views) < 4: continue
            med = statistics.median(views) or 1
            for v, n in zip(vs, views):
                if n >= 1.8 * med:
                    out['outliers'].append(dict(channel=v['snippet']['channelTitle'], title=v['snippet']['title'], views=n, x_median=round(n / med, 1)))
        except Exception as e:
            log.warning('benchmark %s failed: %s', handle, e)
    save_json(cache, DATA / 'channel_ids.json')
    out['outliers'].sort(key=lambda x: -x['x_median'])
    return out


def gather(cfg, yt=None):
    r = cfg['research']
    news = google_news(r['news_queries_india'], 'IN') + google_news(r['news_queries_global'], 'US')
    ytsig = youtube_signals(yt, r['youtube_keywords'], r.get('benchmark_channels', []))
    log.info('signals: %d headlines, %d trending, %d outliers', len(news), len(ytsig['trending']), len(ytsig['outliers']))
    return news, ytsig


def format_signals(news, ytsig):
    n = '\n'.join(f"- [{x['q']}] {x['title']}" for x in news[:60]) or '- (none fetched)'
    t = '\n'.join(f"- {v['title']} — {v['channel']} — {v['views']:,} views ({v['minutes']} min)" for v in ytsig['trending'][:20])
    o = '\n'.join(f"- OUTLIER x{v['x_median']}: {v['title']} — {v['channel']} — {v['views']:,} views" for v in ytsig['outliers'][:20])
    return n, (t + '\n' + o).strip() or '- (YouTube signals unavailable)'
