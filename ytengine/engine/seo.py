"""Title, description (chapters, sources, credits, disclosure) and tags."""


def ts(sec):
    sec = int(sec); h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def chapters(sb, starts):
    out = []
    for i, (sec, st) in enumerate(zip(sb['sections'], starts)):
        out.append(f"{ts(0 if i == 0 else st)} {'Intro' if i == 0 else sec.get('title')}")
    return out


def tags(sb, limit=480):
    seen, out, n = set(), [], 0
    for t in sb.get('tags', []):
        t = str(t).strip().replace('<', '').replace('>', '')[:60]
        if not t or t.lower() in seen: continue
        if n + len(t) + 1 > limit: break
        seen.add(t.lower()); out.append(t); n += len(t) + 1
    return out


def build(sb, section_starts, watch_next, credit_lines, cfg):
    d = [sb.get('description_intro', '').strip(), '', 'CHAPTERS'] + chapters(sb, section_starts)
    if watch_next and watch_next.get('video_id'):
        d += ['', f"▶ Watch next: {watch_next['title']}", f"https://youtu.be/{watch_next['video_id']}"]
    srcs = [s for s in sb.get('sources', []) if isinstance(s, dict) and s.get('url')]
    if srcs:
        d += ['', 'SOURCES'] + [f"- {s.get('title', '').strip()[:90]}: {s['url']}" for s in srcs[:15]]
    d += ['', 'This video is for education and entertainment only. It is not financial, tax or investment advice.']
    if cfg['upload'].get('disclose_synthetic_media', True):
        d += ['Narration is produced with a synthetic (AI) voice. Footage and photos are licensed; credits below.']
    if credit_lines: d += ['', 'CREDITS'] + credit_lines
    hs = [h if str(h).startswith('#') else '#' + str(h) for h in sb.get('hashtags', [])][:3]
    if hs: d += ['', ' '.join(h.replace(' ', '') for h in hs)]
    desc = '\n'.join(d).replace('<', '‹').replace('>', '›')
    return dict(title=sb['title'][:100], description=desc[:4900], tags=tags(sb))
