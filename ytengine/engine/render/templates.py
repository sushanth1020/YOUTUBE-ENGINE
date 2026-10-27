"""Data-driven scene templates.

Every visual "beat" in a storyboard has a `type` and a few parameters. The writer (Claude) only fills
parameters; layout, text fitting, animation and timing are handled here, so any topic renders cleanly.

Each template is draw(c, t, b) where `b` is the beat dict enriched by the timeline with:
  _t0, _t1   absolute start / end time of the beat (seconds, within the section)
  _starts    absolute start times of every sentence spoken during the beat
  _photo     resolved local photo path (person / quote templates)
"""
import math
from .eng import *
from . import fx

CX, CY = W / 2, H / 2 - 40          # visual centre (leaves room for captions at the bottom)
NAMED = dict(green=C['green'], red=C['red'], amber=C['amber'], yellow=C['amber'], gold=C['amber'], blue=C['blue'],
             purple=C['purple'], orange=C['orange'], white=C['white'], text=C['text'], muted=C['muted'], gray=C['muted'],
             grey=C['muted'])


def col(name, default='white'):
    if isinstance(name, int): return name
    return NAMED.get(str(name or default).lower().strip(), NAMED.get(default, C['white']))


# ---------------------------------------------------------------- text helpers
def fit_size(s, fn, max_size, maxw, min_size=22):
    size = max_size
    while size > min_size and tw(s, size, fn) > maxw: size -= 2
    return size


def fit_block(s, fn, max_size, maxw, max_lines=3, min_size=22):
    """Largest size at which `s` wraps into <= max_lines lines of width maxw."""
    size = max_size
    while size > min_size:
        lines = wrap(s, size, fn, maxw)
        if len(lines) <= max_lines and all(tw(l, size, fn) <= maxw for l in lines): return size, lines
        size -= 2
    return size, wrap(s, size, fn, maxw)


def block(c, s, x, y, max_size, fn, color, maxw, max_lines=3, a=1.0, lh=1.12, align='c', shadow=None):
    size, lines = fit_block(s, fn, max_size, maxw, max_lines)
    n = len(lines)
    for i, ln in enumerate(lines):
        text(c, ln, x, y + (i - (n - 1) / 2) * size * lh, size, fn, color, a, align, shadow)
    return size * lh * n


def num(v, prefix='', suffix='', decimals=0):
    try: v = float(v)
    except Exception: return f'{prefix}{v}{suffix}'
    s = f'{v:,.{int(decimals)}f}'
    return f'{prefix}{s}{suffix}'


def abbr(v, prefix='', suffix=''):
    a = abs(v)
    for div, tag in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if a >= div:
            q = v / div
            return f'{prefix}{q:.1f}{tag}{suffix}'.replace('.0' + tag, tag)
    return f'{prefix}{v:g}{suffix}'


def at(b, i, fallback):
    """Absolute time of the i-th sentence inside the beat, or a fallback offset from beat start."""
    st = b.get('_starts') or []
    return st[i] if 0 <= i < len(st) else b['_t0'] + fallback


def stagger(b, n, first=0.3, lead_sentence=1):
    """Reveal times for n items: one per sentence when there are enough sentences, else evenly spaced."""
    st = b.get('_starts') or []
    if len(st) - lead_sentence >= n:
        return [st[lead_sentence + i] for i in range(n)]
    dur = max(1.0, (b['_t1'] or b['_t0'] + 6) - b['_t0'] - 1.0)
    gap = min(1.2, dur / max(n, 1))
    return [b['_t0'] + first + i * gap for i in range(n)]


def wrap_show(c, t, b, fn, x=CX, y=CY, rise=40, d=0.5):
    show(c, t, b['_t0'], b['_t1'], x, y, fn, d=d, rise=rise)


# ---------------------------------------------------------------- templates
def kinetic(c, t, b):
    lines = [l if isinstance(l, dict) else {'text': l} for l in (b.get('lines') or [b.get('text', '')])][:3]
    sub, chips = b.get('sub'), (b.get('chips') or [])[:3]
    sizes = [fit_size(l['text'].upper() if b.get('upper', True) else l['text'], 'mx', l.get('size', 170 if len(lines) < 3 else 130), 1680) for l in lines]
    total = sum(s * 1.08 for s in sizes) + (60 if sub else 0) + (110 if chips else 0)
    y0 = -total / 2

    def draw(c):
        y = y0
        for i, (l, sz) in enumerate(zip(lines, sizes)):
            a = eo(lin(t, b['_t0'] + i * 0.22, b['_t0'] + i * 0.22 + 0.35))
            s_ = l['text'].upper() if b.get('upper', True) else l['text']
            text(c, s_, 0, y + sz * 0.54, sz, 'mx', col(l.get('color'), 'white' if i == 0 else 'amber'), a)
            y += sz * 1.08
        if sub:
            text(c, sub, 0, y + 30, fit_size(sub, 'is', 44, 1500), 'is', C['muted'], eo(lin(t, b['_t0'] + 0.5, b['_t0'] + 0.9)))
            y += 60
        if chips:
            ts = stagger(b, len(chips), first=0.8)
            widths = [tw(ch, 34, 'ib') + 64 for ch in chips]
            x = -(sum(widths) + 40 * (len(chips) - 1)) / 2
            for ch, w_, t_ in zip(chips, widths, ts):
                a, s_, dy = env(t, t_, None, d=0.4)
                if a > 0:
                    with G(c, x + w_ / 2, y + 70 + dy, a, s_): chip(c, 0, 0, ch, col(b.get('chip_color'), 'amber'), 34, fn='ib')
                x += w_ + 40
    wrap_show(c, t, b, draw)


def stat(c, t, b):
    color = col(b.get('color'), 'green')
    v1 = b.get('value', 0); dec = int(b.get('decimals', 0 if float(v1) == int(float(v1)) else 1))
    pre, suf = b.get('prefix', ''), b.get('suffix', '')
    final = num(v1, pre, suf, dec)
    size = fit_size(final, 'mx', 280, 1500)

    def draw(c):
        glow(c, 0, -40, 620, color, 0.2)
        if b.get('kicker'): text(c, b['kicker'].upper(), 0, -size * 0.5 - 90, 48, 'mb', C['muted'])
        v = count(t, b['_t0'] + 0.25, float(b.get('from', 0)), float(v1), 1.2)
        text(c, num(v, pre, suf, dec), 0, -40, size, 'mx', color)
        if b.get('label'): block(c, b['label'], 0, size * 0.5 + 40, 46, 'is', C['text'], 1400, 2)
        if b.get('chip'):
            t_ = at(b, 1, 1.6)
            a, s_, dy = env(t, t_, None, d=0.4)
            if a > 0:
                with G(c, 0, size * 0.5 + 170 + dy, a, s_): chip(c, 0, 0, b['chip'], col(b.get('chip_color'), 'amber'), 32, fn='ib')
    wrap_show(c, t, b, draw)


def report(c, t, b):
    side = b.get('side')
    t_slide = at(b, 1, 2.4) if side else 1e9
    slide = eio(lin(t, t_slide, t_slide + 0.8)) if side else 0
    rows = [(str(r[0]), str(r[1]), bool(r[2]) if len(r) > 2 else False) for r in (b.get('rows') or [])][:4]
    spec = dict(publisher=b.get('publisher', ''), kicker=b.get('kicker', 'REPORT'), title=b.get('title', ''),
                subtitle=b.get('subtitle', ''), rows=rows, band=col(b.get('band'), 'red'), seed=hash(b.get('title', '')) % 97,
                hl_t=at(b, 1, 1.8) if not side else t_slide + 0.4, foot=b.get('foot', 'Stylised for illustration'))
    fx.report_card(c, t, b['_t0'] + 0.1, spec, x=lerp(W / 2, W / 2 - 470, slide), t1=b['_t1'], scale=lerp(1.0, 0.86, slide))
    if side:
        sb = dict(side, _t0=t_slide + 0.3, _t1=b['_t1'], _starts=[s for s in b.get('_starts', []) if s > t_slide])
        color = col(side.get('color'), 'red')
        v1 = side.get('value', 0); dec = int(side.get('decimals', 0 if float(v1) == int(float(v1)) else 1))
        final = num(v1, side.get('prefix', ''), side.get('suffix', ''), dec)
        size = fit_size(final, 'mx', 240, 760)

        def draw(c):
            glow(c, 0, -40, 520, color, 0.2)
            v = count(t, sb['_t0'] + 0.2, 0, float(v1), 1.2)
            text(c, num(v, side.get('prefix', ''), side.get('suffix', ''), dec), 0, -70, size, 'mx', color)
            if side.get('label'): block(c, side['label'], 0, 120, 42, 'is', C['text'], 720, 3)
        show(c, t, sb['_t0'], b['_t1'], W / 2 + 430, CY, draw)


def headline(c, t, b):
    fx.headline_card(c, t, b['_t0'] + 0.05, b.get('outlet', ''), b.get('headline', ''), b.get('date', ''),
                     t1=b['_t1'], w=1560, seed=hash(b.get('headline', '')) % 50)


def person_card(c, t, b):
    ph = b.get('_photo')
    name = b.get('caption') or b.get('name') or ''
    if ph:
        fx.photo_card(c, t, b['_t0'] + 0.1, ph, 450, CY - 60, 470, 520, t1=b['_t1'], rot=-2.5, caption=name,
                      credit=b.get('_credit'), focus=(0.5, 0.32))
        x0, maxw = W / 2 + 300, 960
    else:
        x0, maxw = CX, 1500

    def draw(c):
        y = -150
        if b.get('kicker'): text(c, b['kicker'].upper(), 0, y, 46, 'mb', col(b.get('kicker_color'), 'amber')); y += 110
        if b.get('big'):
            h_ = block(c, b['big'].upper(), 0, y + 60, 150, 'mx', col(b.get('color'), 'white'), maxw, 2); y += h_ + 20
        elif not ph:
            block(c, name.upper(), 0, y + 60, 150, 'mx', C['white'], maxw, 2); y += 180
        if b.get('sub'): block(c, b['sub'], 0, y + 40, 40, 'is', C['muted'], maxw, 2); y += 100
        if b.get('chip'):
            t_ = at(b, 1, 1.8)
            a, s_, dy = env(t, t_, None, d=0.4)
            if a > 0:
                with G(c, 0, y + 50 + dy, a, s_): chip(c, 0, 0, b['chip'], col(b.get('chip_color'), 'amber'), 30, fn='ib')
    show(c, t, b['_t0'] + 0.4, b['_t1'], x0, CY - 40, draw)


def bars(c, t, b):
    items = [(str(i[0]), float(i[1])) for i in (b.get('items') or [])][:7]
    if not items: return
    pre, suf, dec = b.get('prefix', ''), b.get('suffix', ''), int(b.get('decimals', 0))
    hi = b.get('highlight')
    color, hcol = col(b.get('color'), 'blue'), col(b.get('highlight_color'), 'red')
    vmax = max(v for _, v in items) * 1.12 or 1
    n = len(items); bw = min(220, 1400 / n * 0.62); gap = min(300, 1500 / n)
    base, hmax = 230, 420

    def draw(c):
        if b.get('title'): block(c, b['title'].upper(), 0, -370, 46, 'mb', C['text'], 1600, 1)
        if b.get('subtitle'): text(c, b['subtitle'], 0, -315, fit_size(b['subtitle'], 'is', 30, 1500), 'is', C['muted'])
        c.drawLine(-gap * n / 2 - 40, base, gap * n / 2 + 40, base, paint(C['dim'], 1, stroke=3))
        for i, (lab, v) in enumerate(items):
            x = (i - (n - 1) / 2) * gap; t0 = b['_t0'] + 0.5 + i * 0.22
            p = eo(lin(t, t0, t0 + 0.9)); h = hmax * v / vmax * p
            cc = hcol if (hi is not None and i == int(hi)) else color
            if hi is not None and i != int(hi): cc = mix(color, C['dim'], 0.35 * lin(t, b['_t0'] + 2.5, b['_t0'] + 3.0))
            if h > 1:
                c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x - bw / 2, base - h, bw, h), 14, 14), paint(cc))
                text(c, num(v * p, pre, suf, dec), x, base - h - 42, fit_size(num(v, pre, suf, dec), 'mx', 46, gap - 10), 'mx', C['text'])
            text(c, lab, x, base + 45, fit_size(lab, 'mb', 32, gap - 16), 'mb', C['muted'])
    wrap_show(c, t, b, draw, rise=0)


def line(c, t, b):
    series = [s for s in (b.get('series') or []) if len(s.get('values', [])) >= 2][:3]
    if not series: return
    pre, suf = b.get('prefix', ''), b.get('suffix', '')
    L, R, T, B = -760, 420, -250, 250
    vals = [v for s in series for v in s['values']]
    vmin = min(0.0, min(vals)) if b.get('zero', True) else min(vals)
    vmax = max(vals) * 1.08 or 1
    xl = b.get('x_labels') or []
    dur = max(2.0, ((b['_t1'] or b['_t0'] + 8) - b['_t0']) * 0.7)
    prog = eio(lin(t, b['_t0'] + 0.5, b['_t0'] + 0.5 + min(dur, 7)))

    def P(vs): return [(L + i / (len(vs) - 1) * (R - L), B - (v - vmin) / (vmax - vmin) * (B - T)) for i, v in enumerate(vs)]

    def draw(c):
        if b.get('title'): block(c, b['title'].upper(), 0, -360, 46, 'mb', C['text'], 1600, 1)
        for k in range(5):
            v = vmin + (vmax - vmin) * k / 4; y = B - (v - vmin) / (vmax - vmin) * (B - T)
            c.drawLine(L, y, R, y, paint(C['white'], 0.06, stroke=2))
            text(c, abbr(v, pre, suf), L - 20, y, 26, 'im', C['muted'], 1, 'r')
        for i, lab in enumerate(xl):
            x = L + (i / max(1, len(xl) - 1)) * (R - L)
            text(c, str(lab), x, B + 42, 28, 'gx', C['muted'])
        for k, s in enumerate(series):
            cc = col(s.get('color'), ['green', 'red', 'blue'][k])
            e = line_series(c, P(s['values']), prog, cc, 8)
            n = prog * (len(s['values']) - 1); i = min(len(s['values']) - 1, int(n))
            v = s['values'][i] if i >= len(s['values']) - 1 else lerp(s['values'][i], s['values'][i + 1], n - i)
            lab = f"{s.get('label', '')}  {abbr(v, pre, suf)}".strip()
            text(c, lab, e[0] + 26, e[1] + (-30 if k == 0 else 34), fit_size(lab, 'mx', 40, 560), 'mx', cc, 1, 'l')
        if b.get('callout') and t > at(b, 1, dur * 0.8):
            t_ = at(b, 1, dur * 0.8)
            with G(c, -200, -230, eo(lin(t, t_, t_ + 0.4))): chip(c, 0, 0, b['callout'], col(b.get('callout_color'), 'amber'), 34, fn='ib')
    wrap_show(c, t, b, draw, rise=0, y=CY + 10)


def versus(c, t, b):
    sides = [b.get('left') or {}, b.get('right') or {}]
    t_right = at(b, 1, 1.4); win = b.get('winner'); t_win = at(b, 2, 3.2)

    def draw(c):
        for i, sd in enumerate(sides):
            a, s_, dy = env(t, b['_t0'] + 0.1 if i == 0 else t_right, None)
            if a <= 0: continue
            cc = col(sd.get('color'), 'green' if i == 0 else 'red')
            with G(c, (i - 0.5) * 820, dy, a, s_):
                card(c, 0, 0, 720, 500, border=cc)
                block(c, sd.get('title', '').upper(), 0, -160, 50, 'mx', cc, 640, 2)
                if sd.get('value') not in (None, ''):
                    vtxt = str(sd['value']); text(c, vtxt, 0, 10, fit_size(vtxt, 'mx', 140, 640), 'mx', C['text'])
                if sd.get('sub'): block(c, sd['sub'], 0, 150, 34, 'is', C['muted'], 620, 2)
                if win and ((win == 'left' and i == 0) or (win == 'right' and i == 1)) and t > t_win:
                    with G(c, 0, -265, eo(lin(t, t_win, t_win + 0.35))): chip(c, 0, 0, 'WINNER', cc, 32, fn='mx')
        if t > t_right: text(c, 'VS', 0, 0, 70, 'mx', C['text'], eo(lin(t, t_right, t_right + 0.3)))
    wrap_show(c, t, b, draw, rise=0)


def listing(c, t, b):
    items = [str(x) for x in (b.get('items') or [])][:10]
    if not items: return
    ts = stagger(b, len(items), first=0.6, lead_sentence=1 if b.get('title') else 0)
    two = len(items) > 5
    rows = math.ceil(len(items) / (2 if two else 1))
    rh = min(120, 620 / rows); w = 760 if two else 1300
    numbered = b.get('numbered', True)
    cc = col(b.get('color'), 'amber')

    def draw(c):
        top = -rows * rh / 2 + 30
        if b.get('title'): block(c, b['title'].upper(), 0, top - 90, 64, 'mx', C['text'], 1600, 1)
        for i, it in enumerate(items):
            a, s_, dy = env(t, ts[i], None, d=0.4, rise=20)
            if a <= 0: continue
            colx = (i // rows - 0.5) * 820 if two else 0
            y = top + (i % rows) * rh + rh / 2
            latest = i == max([k for k, tt in enumerate(ts) if tt <= t] or [0])
            with G(c, colx, y + dy, a, s_):
                rrect(c, 0, 0, w, rh - 18, 22, rgba(0xFF0B1220, 0.86))
                rrect(c, 0, 0, w, rh - 18, 22, cc if latest else C['dim'], 0.9, stroke=3)
                lx = -w / 2 + 30
                if numbered:
                    c.drawCircle(lx + 32, 0, min(34, rh * 0.3), paint(cc)); text(c, str(i + 1), lx + 32, 0, min(40, rh * 0.36), 'mx', C['bg'], shadow=False)
                    lx += 90
                text(c, it, lx, 0, fit_size(it, 'mx', min(48, rh * 0.42), w - (lx + w / 2) - 30), 'mx', C['text'], 1, 'l')
    wrap_show(c, t, b, draw, rise=0, y=CY + 20)


def quote(c, t, b):
    ph = b.get('_photo')
    if ph:
        fx.photo_card(c, t, b['_t0'] + 0.1, ph, 450, CY - 60, 420, 500, t1=b['_t1'], rot=-3, caption=b.get('author'),
                      credit=b.get('_credit'), focus=(0.5, 0.3))
    x0, maxw = (W / 2 + 320, 900) if ph else (CX, 1500)
    stamp = b.get('stamp'); t_st = at(b, 1, 2.2)

    def draw(c):
        block(c, f'"{b.get("text", "")}"', 0, -80, 72, 'sb', C['text'], maxw, 4)
        if b.get('author') and not ph: text(c, f'— {b["author"]}', 0, 120, 38, 'is', C['muted'])
        if stamp and t > t_st:
            k = eo(lin(t, t_st, t_st + 0.35)); s_ = 1.6 - 0.6 * back(lin(t, t_st, t_st + 0.4))
            sc = col(b.get('stamp_color'), 'red')
            with G(c, 0, 200, k, s_, rot=-8):
                w_ = tw(stamp.upper(), 56, 'mx') + 80
                rrect(c, 0, 0, w_, 120, 14, sc, 1, stroke=8); text(c, stamp.upper(), 0, 0, 56, 'mx', sc)
    show(c, t, b['_t0'] + 0.3, b['_t1'], x0, CY - 40, draw)


def timeline(c, t, b):
    ev = [(str(e[0]), str(e[1])) for e in (b.get('events') or [])][:6]
    if not ev: return
    ts = stagger(b, len(ev), first=0.5, lead_sentence=0)
    L, R = -620, 620

    def draw(c):
        if b.get('title'): block(c, b['title'].upper(), 0, -330, 60, 'mx', C['text'], 1600, 1)
        p = max([i for i, tt in enumerate(ts) if tt <= t] or [-1])
        prog = 0 if p < 0 else (p + eo(lin(t, ts[p], ts[p] + 0.6))) / max(1, len(ev) - 1) if len(ev) > 1 else 1
        rrect(c, 0, 0, R - L, 16, 8, C['card2'])
        if prog > 0: rrect(c, L + (R - L) * min(prog, 1) / 2, 0, (R - L) * min(prog, 1), 16, 8, C['amber'])
        for i, (yr, lab) in enumerate(ev):
            x = L + (R - L) * (i / max(1, len(ev) - 1)); on = t >= ts[i]
            c.drawCircle(x, 0, 22, paint(C['amber'] if on else C['dim']))
            a = eo(lin(t, ts[i], ts[i] + 0.4))
            up = i % 2 == 0
            text(c, yr, x, -70 if up else 70, fit_size(yr, 'gx', 46, (R - L) / len(ev)), 'gx', C['text'], a)
            block(c, lab, x, -150 if up else 160, 30, 'is', C['text'], min(420, (R - L) / max(1, len(ev) - 1) - 20), 3, a=a)
    wrap_show(c, t, b, draw, rise=0)


def icons(c, t, b):
    total = max(1, min(20, int(b.get('total', 10)))); hi = max(0, min(total, int(b.get('highlight', 1))))
    on, off = col(b.get('color_on'), 'red'), col(b.get('color_off'), 'muted')
    per_row = 10 if total > 10 else total
    gap = min(150, 1500 / per_row)

    def draw(c):
        if b.get('big'): text(c, b['big'].upper(), 0, -300, fit_size(b['big'].upper(), 'mx', 150, 1600), 'mx', on)
        if b.get('label'): block(c, b['label'], 0, -190, 42, 'is', C['text'], 1500, 2)
        for i in range(total):
            r_, k = divmod(i, per_row)
            x = (k - (per_row - 1) / 2) * gap; y = 60 + r_ * 190
            p = lin(t, b['_t0'] + 0.6 + i * 0.12, b['_t0'] + 0.9 + i * 0.12)
            person(c, x, y, min(130, gap * 0.9), mix(C['dim'], on if i < hi else off, p))
    wrap_show(c, t, b, draw, rise=0)


def flow(c, t, b):
    nodes = [(str(n[0]), str(n[1]) if len(n) > 1 else '') for n in (b.get('nodes') or [])][:4]
    if len(nodes) < 2: return
    n = len(nodes); gap = min(560, 1560 / (n - 1)); w = min(400, gap - 90); x0n = -(n - 1) / 2 * gap
    ts = stagger(b, n, first=0.2, lead_sentence=0)
    colors = [C['blue'], C['purple'], C['amber'], C['green']]

    def draw(c):
        for i, (lab, sub) in enumerate(nodes):
            x = x0n + i * gap
            a, s_, dy = env(t, ts[i], None, d=0.4)
            if a <= 0: continue
            with G(c, x, dy, a, s_):
                card(c, 0, 0, w, 190, border=colors[i % 4])
                text(c, lab.upper(), 0, -26, fit_size(lab.upper(), 'mx', 44, w - 40), 'mx', colors[i % 4])
                if sub: text(c, sub, 0, 40, fit_size(sub, 'is', 28, w - 40), 'is', C['muted'])
            if i > 0 and t > ts[i]:
                x0 = x0n + (i - 1) * gap + w / 2 + 10; x1 = x - w / 2 - 10
                k = eo(lin(t, ts[i], ts[i] + 0.5))
                c.drawLine(x0, 0, lerp(x0, x1, k), 0, paint(C['white'], 0.7, stroke=6))
                d = ((t - ts[i]) % 1.4) / 1.4
                c.drawCircle(lerp(x0, x1, d), 0, 12, paint(C['white']))
        if b.get('back_label') and t > ts[-1] + 1.0:
            t_ = ts[-1] + 1.0; k = ((t - t_) % 1.3) / 1.3
            text(c, '$', lerp(x0n + (n - 1) * gap, x0n + (n - 2) * gap, k), -150, 64, 'mx', C['green'])
            with G(c, 0, 230, eo(lin(t, t_, t_ + 0.4))): chip(c, 0, 0, b['back_label'], C['green'], 40, fn='mx')
    wrap_show(c, t, b, draw, rise=0)


def footage(c, t, b):
    if b.get('caption'):
        def draw(c):
            block(c, b['caption'].upper(), 0, 0, 110, 'mx', col(b.get('color'), 'white'), 1600, 2)
        wrap_show(c, t, b, draw)


def end(c, t, b):
    thumb = b.get('_next_thumb')

    def draw(c):
        if thumb:
            img = fx.photo(thumb)
            text(c, 'WATCH NEXT', 0, -330, 56, 'mx', C['amber'])
            r = skia.Rect.MakeXYWH(-480, -270, 960, 540)
            rrect(c, 0, 10, 980, 560, 22, 0xFF000000, 0.5)
            c.save(); c.clipRRect(skia.RRect.MakeRectXY(r, 18, 18), True)
            c.drawImageRect(img, r, skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear)); c.restore()
            c.drawRRect(skia.RRect.MakeRectXY(r, 18, 18), paint(C['white'], 0.9, stroke=4))
            by = 345
        else:
            block(c, (b.get('text') or 'THANKS FOR WATCHING').upper(), 0, -120, 110, 'mx', C['text'], 1500, 2)
            by = 120
        t_ = at(b, 1, 1.0)
        if t > t_:
            with G(c, 0, by, eo(lin(t, t_, t_ + 0.3)), 1 + 0.05 * math.sin(t * 5)):
                rrect(c, 0, 0, 520, 120, 60, C['red']); text(c, 'SUBSCRIBE', 0, 0, 58, 'mx', C['white'])
    show(c, t, b['_t0'], None, CX, CY - 60, draw)


TEMPLATES = dict(kinetic=kinetic, stat=stat, report=report, headline=headline, person=person_card, bars=bars, line=line,
                 versus=versus, list=listing, quote=quote, timeline=timeline, icons=icons, flow=flow, footage=footage, end=end)

# Default darkness of the background wash per template (busy foregrounds need darker footage).
WASH = dict(kinetic=0.62, stat=0.66, report=0.76, headline=0.72, person=0.74, bars=0.84, line=0.84, versus=0.8, list=0.82,
            quote=0.72, timeline=0.82, icons=0.8, flow=0.84, footage=0.38, end=0.78)
