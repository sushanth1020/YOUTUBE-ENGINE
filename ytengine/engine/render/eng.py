import skia, math, re, os
from pathlib import Path
W, H, FPS = 1920, 1080, 30
F = str(Path(__file__).resolve().parents[2] / 'fonts') + os.sep
# v2: Inter -> Geist for body, labels, captions and numbers; serif for headline/report cards
TF = {'mx': F+'Montserrat-ExtraBold.ttf', 'mb': F+'Montserrat-Bold.ttf', 'ms': F+'Montserrat-SemiBold.ttf',
      'ib': F+'Geist-Bold.ttf', 'is': F+'Geist-SemiBold.ttf', 'im': F+'Geist-Medium.ttf',
      'gx': F+'Geist-ExtraBold.ttf', 'gr': F+'Geist-Regular.ttf',
      'sb': F+'SourceSerif4-Bold.ttf', 'ss': F+'SourceSerif4-SemiBold.ttf'}
_tf = {k: skia.Typeface.MakeFromFile(v) for k, v in TF.items()}
_fc = {}
def font(n, s):
    k = (n, round(s, 1))
    if k not in _fc:
        f = skia.Font(_tf[n], s); f.setSubpixel(True); f.setEdging(skia.Font.Edging.kAntiAlias); _fc[k] = f
    return _fc[k]

C = dict(bg=0xFF0B1220, card=0xFF131D33, card2=0xFF1A2742, green=0xFF22C55E, red=0xFFEF4444,
         amber=0xFFF59E0B, text=0xFFF1F5F9, muted=0xFF94A3B8, dim=0xFF475569, purple=0xFFA855F7,
         orange=0xFFF97316, blue=0xFF60A5FA, white=0xFFFFFFFF)

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def lin(t, t0, t1): return clamp((t - t0) / (t1 - t0)) if t1 > t0 else float(t >= t0)
def eo(p): return 1 - (1 - p) ** 3
def ei(p): return p ** 3
def eio(p): return 4 * p ** 3 if p < .5 else 1 - (-2 * p + 2) ** 3 / 2
def back(p, s=1.4):
    q = p - 1; return 1 + (s + 1) * q ** 3 + s * q ** 2
def lerp(a, b, p): return a + (b - a) * p
def count(t, t0, v0, v1, d=1.0): return lerp(v0, v1, eo(lin(t, t0, t0 + d)))

def rgba(c, a=1.0):
    return (c & 0x00FFFFFF) | (int(((c >> 24) & 255) * clamp(a)) << 24)
def mix(c1, c2, p):
    p = clamp(p); out = 0
    for sh in (24, 16, 8, 0):
        out |= int(lerp((c1 >> sh) & 255, (c2 >> sh) & 255, p)) << sh
    return out
def paint(c, a=1.0, stroke=None):
    p = skia.Paint(AntiAlias=True, Color=rgba(c, a))
    if stroke:
        p.setStyle(skia.Paint.kStroke_Style); p.setStrokeWidth(stroke)
        p.setStrokeCap(skia.Paint.kRound_Cap); p.setStrokeJoin(skia.Paint.kRound_Join)
    return p

def env(t, t0, t1=None, d=0.5, dout=0.3, rise=40):
    """alpha, scale, dy for an element visible from t0 until t1 (exit)."""
    if t < t0: return 0.0, 0.82, rise
    p = clamp((t - t0) / d); a = eo(clamp((t - t0) / (d * 0.6)))
    s = 0.82 + 0.18 * back(p); dy = rise * (1 - eo(p))
    if t1 is not None and t > t1:
        q = ei(clamp((t - t1) / dout)); a *= 1 - q; s *= 1 - 0.06 * q; dy -= 30 * q
    return a, s, dy

class G:
    def __init__(self, c, x=0, y=0, a=1.0, s=1.0, rot=0):
        self.c, self.x, self.y, self.a, self.s, self.rot = c, x, y, a, s, rot
    def __enter__(self):
        c = self.c; c.save()
        if self.a < 0.999: c.saveLayerAlpha(None, int(255 * clamp(self.a)))
        c.translate(self.x, self.y)
        if self.rot: c.rotate(self.rot)
        if self.s != 1: c.scale(self.s, self.s)
        return c
    def __exit__(self, *e):
        self.c.restore()
        if self.a < 0.999: self.c.restore()

def show(c, t, t0, t1, x, y, fn, d=0.5, rise=40):
    a, s, dy = env(t, t0, t1, d=d, rise=rise)
    if a <= 0.002: return False
    with G(c, x, y + dy, a, s): fn(c)
    return True

TABRE = re.compile(r"^[+\-−≈ ]*\$?[\d,\.]+[%KMB]?$")
SHADOW = [True]
def _tab_w(s, f):
    dw = f.measureText('0'); return sum(dw if ch.isdigit() else f.measureText(ch) for ch in s)
def tw(s, size, fn='mx'):
    f = font(fn, size)
    return _tab_w(s, f) if TABRE.match(s) else f.measureText(s)
def _draw(c, s, x, y, f, p):
    if TABRE.match(s):  # tabular figures: every digit sits in a fixed-width slot, so counters don't jitter
        dw = f.measureText('0')
        for ch in s:
            if ch.isdigit():
                gw = f.measureText(ch); c.drawString(ch, x + (dw - gw) / 2, y, f, p); x += dw
            else:
                c.drawString(ch, x, y, f, p); x += f.measureText(ch)
    else: c.drawString(s, x, y, f, p)
def text(c, s, x, y, size, fn='mx', col=None, a=1.0, align='c', shadow=None):
    col = C['text'] if col is None else col
    f = font(fn, size); w = tw(s, size, fn)
    if align == 'c': x -= w / 2
    elif align == 'r': x -= w
    yb = y + size * 0.36
    if (SHADOW[0] if shadow is None else shadow) and size >= 34 and a > 0.02:
        _draw(c, s, x, yb + max(2, size * 0.035), f, paint(0xFF000000, 0.45 * a))
    _draw(c, s, x, yb, f, paint(col, a))
    return w

def wrap(s, size, fn, maxw):
    words, lines, cur = s.split(), [], ''
    for w_ in words:
        cand = (cur + ' ' + w_).strip()
        if tw(cand, size, fn) <= maxw or not cur: cur = cand
        else: lines.append(cur); cur = w_
    if cur: lines.append(cur)
    return lines

def mtext(c, s, x, y, size, fn='mx', col=None, maxw=1500, lh=1.15, a=1.0):
    lines = wrap(s, size, fn, maxw); n = len(lines)
    for i, ln in enumerate(lines):
        text(c, ln, x, y + (i - (n - 1) / 2) * size * lh, size, fn, col, a)

def rrect(c, cx, cy, w, h, r, col, a=1.0, stroke=None):
    c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(cx - w / 2, cy - h / 2, w, h), r, r), paint(col, a, stroke))

def card(c, cx, cy, w, h, col=None, a=1.0, border=None):
    col = C['card'] if col is None else col
    rrect(c, cx, cy + 10, w, h, 28, 0xFF000000, 0.35 * a)
    rrect(c, cx, cy, w, h, 28, col, a)
    if border: rrect(c, cx, cy, w, h, 28, border, 0.9 * a, stroke=3)

def glow(c, x, y, r, col, a=0.35):
    sh = skia.GradientShader.MakeRadial((x, y), r, [rgba(col, a), rgba(col, 0)])
    c.drawCircle(x, y, r, skia.Paint(Shader=sh, AntiAlias=True))

def person(c, x, y, h, col, a=1.0):
    c.drawCircle(x, y - h * 0.3, h * 0.17, paint(col, a))
    rrect(c, x, y + h * 0.17, h * 0.56, h * 0.46, h * 0.22, col, a)

def line_series(c, pts, prog, col, width=8):
    prog = clamp(prog)
    if prog <= 0: return pts[0]
    n = len(pts) - 1; k = prog * n; i = int(k)
    path = skia.Path(); path.moveTo(*pts[0])
    for j in range(1, min(i, n) + 1): path.lineTo(*pts[j])
    if i < n:
        fx = k - i; p0, p1 = pts[i], pts[i + 1]
        end = (lerp(p0[0], p1[0], fx), lerp(p0[1], p1[1], fx)); path.lineTo(*end)
    else: end = pts[-1]
    c.drawPath(path, paint(col, 0.16, stroke=width * 4))
    c.drawPath(path, paint(col, 1, stroke=width))
    c.drawCircle(end[0], end[1], width * 1.4, paint(col))
    c.drawCircle(end[0], end[1], width * 2.8, paint(col, 0.25))
    return end

def area_between(c, top, bot, prog, col, a=0.3):
    prog = clamp(prog)
    if prog <= 0: return
    n = len(top) - 1; k = prog * n; i = int(k)
    def pt(arr, j, fx=0):
        if j >= n: return arr[n]
        return (lerp(arr[j][0], arr[j + 1][0], fx), lerp(arr[j][1], arr[j + 1][1], fx))
    fx = k - i
    T = top[:i + 1] + [pt(top, i, fx)]; B = bot[:i + 1] + [pt(bot, i, fx)]
    path = skia.Path(); path.moveTo(*T[0])
    for p in T[1:]: path.lineTo(*p)
    for p in reversed(B): path.lineTo(*p)
    path.close(); c.drawPath(path, paint(col, a))

def make_bg():
    s = skia.Surface(W + 160, H + 160); c = s.getCanvas()
    c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeLinear([(0, 0), (0, H + 160)], [0xFF101A2F, 0xFF070C17])))
    gp = paint(0xFFFFFFFF, 0.03, stroke=1.5)
    for x in range(0, W + 161, 80): c.drawLine(x, 0, x, H + 160, gp)
    for y in range(0, H + 161, 80): c.drawLine(0, y, W + 160, y, gp)
    c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeRadial((W / 2 + 80, H / 2 + 80), 1300, [0x00000000, 0xC0000000])))
    return s.makeImageSnapshot()
BG = make_bg()
def background(c, t):
    c.drawImage(BG, -80 + 30 * math.sin(t * 0.13), -80 + 22 * math.cos(t * 0.1))

NUMRE = re.compile(r"^\$?\d[\d,\.]*%?$")
def captions(c, t, segs, offset):
    tt = t - offset; cur = None
    for sg in segs:
        if sg['start'] - 0.05 <= tt < sg['end'] + 0.28: cur = sg; break
    if not cur: return
    size, fn, maxw = 40, 'is', 1500
    lines = wrap(cur['text'], size, fn, maxw)
    chunks = [lines[i:i + 2] for i in range(0, len(lines), 2)]
    total = sum(len(' '.join(ch)) for ch in chunks); dur = cur['end'] - cur['start']; acc = 0; pick = chunks[-1]
    for ch in chunks:
        L = len(' '.join(ch)) / total * dur
        if tt < cur['start'] + acc + L: pick = ch; break
        acc += L
    a = eo(lin(tt, cur['start'] - 0.05, cur['start'] + 0.1))
    boxw = max(tw(l, size, fn) for l in pick) + 70; boxh = len(pick) * size * 1.3 + 34
    cy = 1000 - boxh / 2
    rrect(c, W / 2, cy, boxw, boxh, 18, 0xFF000000, 0.62 * a)
    for i, ln in enumerate(pick):
        y = cy + (i - (len(pick) - 1) / 2) * size * 1.3
        x = W / 2 - tw(ln, size, fn) / 2
        prev = ''
        for wd in ln.split(' '):
            core = wd.rstrip(',.?!:;'); tail = wd[len(core):]
            hot = (NUMRE.match(core) or core.lower() == 'zero') and not prev.endswith('S&P')
            text(c, core, x, y, size, fn, C['amber'] if hot else C['white'], a, align='l'); x += tw(core, size, fn)
            if tail: text(c, tail, x, y, size, fn, C['white'], a, align='l'); x += tw(tail, size, fn)
            x += tw(' ', size, fn); prev = core

def title_card(c, t, num, title, dur=2.0):
    a, s, dy = env(t, 0.05, dur - 0.3, d=0.55)
    if a <= 0: return
    with G(c, W / 2, H / 2 - 30 + dy, a, s):
        glow(c, 0, 0, 700, C['amber'], 0.10)
        text(c, num, 0, -120, 64, 'mx', C['amber'])
        wl = eo(lin(t, 0.25, 0.9)) * 220
        c.drawLine(-wl, -60, wl, -60, paint(C['amber'], 1, stroke=6))
        mtext(c, title.upper(), 0, 40, 92, 'mx', C['text'], maxw=1500)

def source(c, t, txt, t0, t1):
    a, _, _ = env(t, t0, t1, d=0.4, rise=0)
    if a > 0:
        w = tw(txt, 22, 'im')
        rrect(c, 70 + w / 2 + 6, 60, w + 36, 40, 20, 0xFF000000, 0.45 * a)
        text(c, txt, 76, 60, 22, 'im', 0xFFCBD5E1, a, align='l')

def chip(c, x, y, s, col, size=40, fn='mb', a=1.0, fill=None):
    w = tw(s, size, fn) + 64
    rrect(c, x, y, w, size * 1.9, size * 0.95, fill if fill else rgba(mix(0xFF0B1220, col, 0.2), 0.9), a)
    rrect(c, x, y, w, size * 1.9, size * 0.95, col, 0.9 * a, stroke=3)
    text(c, s, x, y, size, fn, col, a)

def big_line(c, t, t0, t1, s, size=150, col=None, y=H / 2 - 40, fn='mx'):
    show(c, t, t0, t1, W / 2, y, lambda c: mtext(c, s, 0, 0, size, fn, col, maxw=1650))
