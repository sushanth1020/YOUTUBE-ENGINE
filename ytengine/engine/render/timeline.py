"""Turns one storyboard section (+ its voice timing) into an mp4 clip.

Sections are independent, so the pipeline renders them in parallel processes and concatenates them.
"""
import subprocess, time, math, json, sys
import skia
from .eng import *
from . import fx
from .templates import TEMPLATES, WASH
from ..captions import chunk_words, NUM_RE

CHAPTER_LEAD = 2.0   # seconds of chapter title card before the voice starts (sections after the hook)
TAIL = 0.6           # breathing room after the last word of a section


def section_layout(sec, timing, lead):
    """Absolute beat windows + sentence start times inside the section clip."""
    segs = timing['segs']; n = len(segs)
    dur = lead + timing['dur'] + TAIL
    starts = [lead + s['start'] for s in segs]
    beats = []
    for i, b in enumerate(sec['beats']):
        a = max(0, min(n - 1, int(b.get('at', 0))))
        t0 = starts[a] if not (i == 0) else (lead if lead > 0 else 0.0)
        beats.append(dict(b, _at=a, _t0=t0))
    for i, b in enumerate(beats):
        nxt = beats[i + 1]['_t0'] if i + 1 < len(beats) else None
        b['_t1'] = nxt
        hi = nxt if nxt is not None else dur + 1
        b['_starts'] = [s for s in starts if b['_t0'] - 0.01 <= s < hi]
    return beats, dur


def build_plates(sec, beats, lead):
    plates, last = [], None
    def key(bg): return json.dumps(bg, sort_keys=True) if bg else None
    # chapter card background: the section's own bg, else the first beat's
    if lead > 0:
        bg = sec.get('_bg') or (beats[0].get('_bg') if beats else None)
        if bg: plates.append([0.0, None, bg, dict(wash=0.55)]); last = key(bg)
    for b in beats:
        bg = b.get('_bg')
        if not bg:
            if plates and plates[-1][1] is None: plates[-1][1] = b['_t0']
            last = None; continue
        wash = float(b.get('wash', WASH.get(b['type'], 0.7)))
        if key(bg) == last and plates:   # same footage continues across beats
            plates[-1][3]['wash'] = max(plates[-1][3]['wash'], wash) if b['type'] != 'footage' else plates[-1][3]['wash']
            continue
        if plates and plates[-1][1] is None: plates[-1][1] = b['_t0']
        o = dict(wash=wash)
        if b.get('tag'): o['tag'] = tuple(b['tag'])[:2] if isinstance(b['tag'], (list, tuple)) else (b['tag'],)
        if bg[0] == 'p': o['kb'] = ((0.5, 0.5, 1.04), (0.5 + 0.06 * math.sin(len(plates)), 0.44, 1.16))
        plates.append([b['_t0'], None, bg, o]); last = key(bg)
    return [tuple(p) for p in plates]


def caption_chunks(timing, lead):
    words = timing.get('words') or []
    return [dict(ch, s=ch['s'] + lead, e=ch['e'] + lead) for ch in chunk_words(words)]


def draw_captions(c, t, chunks):
    cur = None
    for ch in chunks:
        if ch['s'] - 0.05 <= t < ch['e'] + 0.25: cur = ch; break
    if not cur: return
    size, fn, maxw = 42, 'is', 1500
    words = cur['words']
    # lay out words into <=2 lines
    lines, line, wsum = [], [], 0
    for w in words:
        ww = tw(w['w'], size, fn) + tw(' ', size, fn)
        if line and wsum + ww > maxw: lines.append(line); line, wsum = [], 0
        line.append(w); wsum += ww
    if line: lines.append(line)
    a = eo(lin(t, cur['s'] - 0.05, cur['s'] + 0.1))
    sp = tw(' ', size, fn)
    def lw(ln): return sum(tw(w['w'], size, fn) for w in ln) + sp * (len(ln) - 1)
    boxw = max(lw(ln) for ln in lines) + 60
    boxh = len(lines) * size * 1.3 + 34
    cy = 1000 - boxh / 2
    rrect(c, W / 2, cy, boxw, boxh, 18, 0xFF000000, 0.62 * a)
    for i, ln in enumerate(lines):
        y = cy + (i - (len(lines) - 1) / 2) * size * 1.3
        x = W / 2 - lw(ln) / 2
        for w in ln:
            core = w['w'].rstrip(',.?!:;"\'')
            speaking = w['s'] - 0.02 <= t < w['e'] + 0.05
            hot = bool(NUM_RE.match(core))
            colr = C['amber'] if (hot or speaking) else C['white']
            text(c, w['w'], x, y, size, fn, colr, a, align='l', shadow=False)
            x += tw(w['w'], size, fn) + sp


def render_section(job):
    """job: dict(sec, timing, lead, chapter_no, out, burn_captions, grain, fps, preview_t=None)"""
    sec, timing, lead = job['sec'], job['timing'], job['lead']
    beats, dur = section_layout(sec, timing, lead)
    plates = build_plates(sec, beats, lead)
    chunks = caption_chunks(timing, lead) if job.get('burn_captions', True) else []
    title = sec.get('title')

    def frame(cv, t, fi):
        cv.clear(C['bg'])
        background(cv, t)
        fx.plates(cv, t, plates)
        z = 1 + 0.025 * (t / max(dur, 1))
        cv.save(); cv.translate(W / 2, H / 2); cv.scale(z, z); cv.translate(-W / 2, -H / 2)
        if lead > 0 and title: title_card(cv, t, f"{job['chapter_no']:02d}", title, dur=lead)
        for b in beats:
            if t < b['_t0'] - 0.05: continue
            if b['_t1'] is not None and t > b['_t1'] + 0.6: continue
            fn = TEMPLATES.get(b['type'])
            if fn:
                try: fn(cv, t, b)
                except Exception as e:  # a bad parameter must never kill the render
                    if not b.get('_warned'): print(f"[render] beat {b['type']} failed: {e}", file=sys.stderr); b['_warned'] = 1
            if b.get('source'): source(cv, t, str(b['source']), b['_t0'], b['_t1'])
        cv.restore()
        draw_captions(cv, t, chunks)
        if job.get('grain', True): fx.grain(cv, fi)

    surf = skia.Surface(W, H); cv = surf.getCanvas()
    if job.get('preview_t') is not None:
        for tt in job['preview_t']:
            frame(cv, tt, int(tt * FPS)); surf.makeImageSnapshot().save(f"{job['out']}_{tt:.1f}.png")
        fx.close_all(); return job['out']
    n = int(math.ceil(dur * FPS))
    pix = 'bgra' if surf.imageInfo().colorType() == skia.kBGRA_8888_ColorType else 'rgba'
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', pix, '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', job.get('preset', 'veryfast'),
                          '-crf', str(job.get('crf', 19)), '-pix_fmt', 'yuv420p', job['out']], stdin=subprocess.PIPE)
    t0 = time.time()
    for i in range(n):
        frame(cv, i / FPS, i)
        p.stdin.write(surf.makeImageSnapshot().tobytes())
    p.stdin.close(); p.wait(); fx.close_all()
    if p.returncode != 0: raise RuntimeError(f'ffmpeg failed for {job["out"]}')
    return dict(out=job['out'], frames=n, dur=n / FPS, secs=round(time.time() - t0, 1))
