"""Validate + repair the storyboard JSON produced by the writer, so the renderer never crashes on it."""
from .render.templates import TEMPLATES

REQUIRED_TOP = ['title', 'sections', 'thumbnail', 'description_intro']


class StoryboardError(ValueError):
    pass


def problems(sb):
    errs = []
    for k in REQUIRED_TOP:
        if k not in sb: errs.append(f'missing top-level field "{k}"')
    secs = sb.get('sections') or []
    if len(secs) < 3: errs.append('need at least 3 sections (hook + 2 chapters)')
    for i, s in enumerate(secs):
        if not s.get('sentences'): errs.append(f'section {i} has no sentences')
        if not s.get('beats'): errs.append(f'section {i} has no beats')
        if i > 0 and not s.get('title'): errs.append(f'section {i} needs a chapter title')
        for j, b in enumerate(s.get('beats') or []):
            if b.get('type') not in TEMPLATES: errs.append(f'section {i} beat {j}: unknown type "{b.get("type")}"')
            if not isinstance(b.get('at', 0), int): errs.append(f'section {i} beat {j}: "at" must be an integer sentence index')
    if len(sb.get('title', '')) > 100: errs.append('title longer than 100 characters')
    return errs


def _num(v):
    if isinstance(v, (int, float)): return float(v)
    s = str(v).replace(',', '').replace('₹', '').replace('$', '').replace('%', '').strip()
    mult = 1
    for suf, m in (('cr', 1e7), ('lakh', 1e5), ('k', 1e3), ('m', 1e6), ('b', 1e9), ('t', 1e12)):
        if s.lower().endswith(suf): s, mult = s[:-len(suf)].strip(), m; break
    return float(s) * mult


def _sanitize(b):
    """Coerce numeric fields; return None if the beat can't be rendered as specified."""
    t = b['type']
    try:
        if t == 'stat': b['value'] = _num(b.get('value', 0))
        if t == 'report' and b.get('side'): b['side']['value'] = _num(b['side'].get('value', 0))
        if t == 'bars': b['items'] = [[str(i[0]), _num(i[1])] for i in b.get('items', []) if len(i) >= 2]
        if t == 'line':
            for srs in b.get('series', []): srs['values'] = [_num(v) for v in srs.get('values', [])]
        if t == 'icons': b['total'] = int(_num(b.get('total', 10))); b['highlight'] = int(_num(b.get('highlight', 1)))
    except Exception:
        txt = b.get('label') or b.get('title') or b.get('text') or ''
        return dict(type='kinetic', at=b.get('at', 0), lines=[str(b.get('value', ''))[:30], str(txt)[:40]], bg=b.get('bg')) if txt else None
    return b


def normalize(sb):
    """Fix what can be fixed automatically. Raises StoryboardError for structural problems."""
    fatal = [e for e in problems(sb) if 'missing top-level' in e or 'no sentences' in e or 'at least 3' in e]
    if fatal: raise StoryboardError('; '.join(fatal))
    sb['title'] = sb['title'][:100]
    for i, s in enumerate(sb['sections']):
        s['sentences'] = [str(x).strip() for x in s['sentences'] if str(x).strip()]
        n = len(s['sentences'])
        if i > 0 and not s.get('title'): s['title'] = f'Part {i}'
        beats = []
        for b in s.get('beats') or []:
            if not isinstance(b, dict): continue
            t = b.get('type')
            if t not in TEMPLATES:
                # unknown visual -> keep the words on screen rather than drop the moment
                b = dict(type='kinetic', lines=[b.get('text') or b.get('title') or ''], bg=b.get('bg'), at=b.get('at', 0))
                if not b['lines'][0]: continue
            try: b['at'] = max(0, min(n - 1, int(b.get('at', 0))))
            except Exception: b['at'] = 0
            b = _sanitize(b)
            if b: beats.append(b)
        if not beats: beats = [dict(type='footage', at=0, bg=s.get('bg'))]
        beats.sort(key=lambda b: b['at'])
        beats[0]['at'] = 0
        # two beats on the same sentence: keep the later (more specific) one
        dedup = {}
        for b in beats: dedup[b['at']] = b
        s['beats'] = [dedup[k] for k in sorted(dedup)]
    last = sb['sections'][-1]
    if not any(b['type'] == 'end' for b in last['beats']):
        last['beats'].append(dict(type='end', at=max(0, len(last['sentences']) - 1)))
        dedup = {b['at']: b for b in last['beats']}; last['beats'] = [dedup[k] for k in sorted(dedup)]
    th = sb['thumbnail']
    th['lines'] = [str(x) for x in (th.get('lines') or [sb['title']])][:3]
    sb.setdefault('tags', []); sb.setdefault('hashtags', []); sb.setdefault('sources', []); sb.setdefault('alt_titles', [])
    return sb


def word_count(sb):
    return sum(len(' '.join(s['sentences']).split()) for s in sb['sections'])
