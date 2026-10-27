# v2 visual layer: full-bleed footage/photo plates with dark wash, film grain,
# report cards, headline cards, photo cards and lower-third tags.
import subprocess, math, random
import numpy as np, skia
from .eng import *
PAPER, INK, INK2, HL = 0xFFF3EFE6, 0xFF14171F, 0xFF5B6170, 0xFFFFD54A

# ---------------- colour grade for footage ----------------
def _sat_matrix(s, gain=1.0):
    r, g, b = 0.2126 * (1 - s), 0.7152 * (1 - s), 0.0722 * (1 - s)
    return [gain * (r + s), gain * g, gain * b, 0, 0,
            gain * r, gain * (g + s), gain * b, 0, 0,
            gain * r, gain * g, gain * (b + s), 0, 0,
            0, 0, 0, 1, 0]
GRADE = skia.ColorFilters.Matrix(_sat_matrix(0.55, 0.95))

# ---------------- sources ----------------
class Clip:
    """Sequential ffmpeg decoder (pre-graded 1920x1080/30fps mp4 -> raw bgra frames)."""
    def __init__(self, path):
        self.path, self.p, self.i, self.img = str(path), None, -1, None
    def _open(self):
        if self.p: self.p.kill()
        self.p = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-stream_loop', '-1', '-i', self.path,
                                   '-f', 'rawvideo', '-pix_fmt', 'bgra', '-'], stdout=subprocess.PIPE, bufsize=W * H * 4 * 2)
        self.i = -1
    def frame(self, idx):
        if self.p is None or idx < self.i: self._open()
        buf = None
        while self.i < idx:
            buf = self.p.stdout.read(W * H * 4); self.i += 1
        if buf is not None and len(buf) == W * H * 4:
            arr = np.frombuffer(buf, np.uint8).reshape(H, W, 4).copy()
            self.img = skia.Image.fromarray(arr, colorType=skia.kBGRA_8888_ColorType)
        return self.img
    def close(self):
        if self.p: self.p.kill(); self.p = None

_photos = {}
def photo(path):
    path = str(path)
    if path not in _photos: _photos[path] = skia.Image.open(path)
    return _photos[path]

# ---------------- plates ----------------
# plate = (t0, t1, src, opts); src = ('v', clip_path) or ('p', photo_path).
# opts: wash (0..1 navy wash strength), kb ((x0,y0,z0),(x1,y1,z1)) Ken Burns for photos, fade, tag (lower-third label)
_decoders = {}
def _dec(key, path):
    if key not in _decoders: _decoders[key] = Clip(path)
    return _decoders[key]

def plate_alpha(t, t0, t1, fade=0.45):
    a = eo(lin(t, t0, t0 + fade))
    if t1 is not None: a *= 1 - ei(lin(t, t1 - fade * 0.6, t1 + fade * 0.4))
    return a

def draw_plate(c, t, t0, t1, src, o):
    a = plate_alpha(t, t0, t1, o.get('fade', 0.45))
    if a <= 0.003: return 0
    kind, name = src
    c.save()
    if a < 0.999: c.saveLayerAlpha(None, int(255 * a))
    p = skia.Paint(ColorFilter=GRADE, AntiAlias=True)
    span = (t1 if t1 is not None else t0 + 12) - t0
    q = clamp((t - t0) / max(span, 0.1))
    if kind == 'v':
        img = _dec((name, round(t0, 3)), name).frame(int(max(0, t - t0 + o.get('skip', 0)) * FPS))
        if img is not None:
            z = lerp(1.0, o.get('zoom', 1.06), q)  # slow push on footage too
            c.save(); c.translate(W / 2, H / 2); c.scale(z, z); c.translate(-W / 2, -H / 2)
            c.drawImage(img, 0, 0, skia.SamplingOptions(skia.FilterMode.kLinear), p); c.restore()
    else:
        img = photo(name)
        (x0, y0, z0), (x1, y1, z1) = o.get('kb', ((0.5, 0.5, 1.04), (0.5, 0.45, 1.16)))
        e = eio(q); cx, cy, z = lerp(x0, x1, e), lerp(y0, y1, e), lerp(z0, z1, e)
        sc = max(W / img.width(), H / img.height()) * z
        w, h = img.width() * sc, img.height() * sc
        left = clamp(W / 2 - cx * w, W - w, 0); top = clamp(H / 2 - cy * h, H - h, 0)
        c.drawImageRect(img, skia.Rect.MakeXYWH(left, top, w, h), skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear), p)
    # dark navy wash + bottom/top gradient + vignette
    wash = o.get('wash', 0.6)
    c.drawRect(skia.Rect.MakeWH(W, H), paint(C['bg'], wash))
    c.drawRect(skia.Rect.MakeWH(W, H), WASH_GRAD)
    if a < 0.999: c.restore()
    c.restore()
    tag = o.get('tag')
    if tag: lower_third(c, t, t0 + 0.5, t1, *tag) if isinstance(tag, tuple) else lower_third(c, t, t0 + 0.5, t1, tag)
    return a

WASH_GRAD = skia.Paint(Shader=skia.GradientShader.MakeLinear(
    [(0, 0), (0, H)], [0x99070C17, 0x00070C17, 0x00070C17, 0xCC070C17], [0, 0.28, 0.62, 1.0]))

def plates(c, t, lst):
    for (t0, t1, src, o) in lst:
        if t >= t0 - 0.01 and (t1 is None or t <= t1 + 0.5):
            draw_plate(c, t, t0, t1, src, o)

def close_all():
    for d in _decoders.values(): d.close()
    _decoders.clear()

# ---------------- lower third ----------------
def lower_third(c, t, t0, t1, label, sub=None):
    a = eo(lin(t, t0, t0 + 0.45))
    if t1 is not None: a *= 1 - ei(lin(t, t1 - 0.5, t1 - 0.1))
    if a <= 0: return
    x, y = 90, 860
    wl = eo(lin(t, t0, t0 + 0.6)) * 70
    c.drawRect(skia.Rect.MakeXYWH(x, y - 30, wl, 5), paint(C['amber'], a))
    text(c, label.upper(), x, y + 8, 30, 'ib', C['white'], a, align='l')
    if sub: text(c, sub, x, y + 48, 24, 'im', C['muted'], a, align='l', shadow=False)

# ---------------- film grain ----------------
def _grain_tiles(n=8, w=W // 2, h=H // 2, sd=34, seed=11):
    rng = np.random.default_rng(seed); out = []
    for _ in range(n):
        g = np.clip(128 + rng.normal(0, sd, (h, w)), 0, 255).astype(np.uint8)
        arr = np.dstack([g, g, g, np.full_like(g, 255)])
        out.append(skia.Image.fromarray(np.ascontiguousarray(arr), colorType=skia.kRGBA_8888_ColorType))
    return out
GRAIN = _grain_tiles()
_VIG = skia.Paint(Shader=skia.GradientShader.MakeRadial((W / 2, H / 2), 1250, [0x00000000, 0x00000000, 0x8C000000], [0, 0.55, 1.0]))
def grain(c, frame_i, strength=0.22):
    c.drawRect(skia.Rect.MakeWH(W, H), _VIG)
    img = GRAIN[(frame_i * 5) % len(GRAIN)]
    p = skia.Paint(BlendMode=skia.BlendMode.kOverlay, Alphaf=strength)
    ox, oy = (frame_i * 37) % 2, (frame_i * 53) % 2
    c.drawImageRect(img, skia.Rect.MakeXYWH(-ox, -oy, W + 2, H + 2), skia.SamplingOptions(skia.FilterMode.kLinear), p)

# ---------------- paper helpers ----------------
def _shadow(c, rect, r=6, a=0.55, dy=24, blur=28):
    p = skia.Paint(AntiAlias=True, Color=rgba(0xFF000000, a), MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    c.drawRRect(skia.RRect.MakeRectXY(rect.makeOffset(0, dy), r, r), p)

def _bars(c, x, y, w, n, seed, lh=26, h=10, col=0xFFC9C4B8, a=1.0):
    r = random.Random(seed)
    for i in range(n):
        ww = w * (r.uniform(0.55, 0.98) if i < n - 1 else r.uniform(0.3, 0.6))
        rrect(c, x + ww / 2, y + i * lh, ww, h, h / 2, col, a)

def highlight(c, x, y, w, h, p, col=HL, a=0.55):
    if p <= 0: return
    c.drawRect(skia.Rect.MakeXYWH(x - 8, y - h / 2, (w + 16) * p, h), paint(col, a))

# ---------------- report card ----------------
def report_card(c, t, t0, spec, x=W / 2, y=H / 2 - 75, t1=None, scale=1.0):
    """A stylised research-report page that slides in, gets its key figure highlighted, then the camera pushes in.
    spec: publisher, title, subtitle, kicker, rows [(label, value, hot)], hl_t (abs time), foot, seed"""
    a, s, dy = env(t, t0, t1, d=0.7, rise=120)
    if a <= 0.002: return
    pw, ph = 900, 880
    push = 1 + 0.10 * eio(lin(t, spec.get('hl_t', t0 + 1.5), spec.get('hl_t', t0 + 1.5) + 2.2))
    rot = lerp(-6, -2.0, eo(lin(t, t0, t0 + 0.9)))
    with G(c, x, y + dy + 30, a, s * scale * 0.82 * push, rot=rot):
        rect = skia.Rect.MakeXYWH(-pw / 2, -ph / 2, pw, ph)
        _shadow(c, rect)
        c.drawRRect(skia.RRect.MakeRectXY(rect, 6, 6), paint(PAPER))
        L = -pw / 2 + 70
        band = spec.get('band', C['blue'])
        c.drawRect(skia.Rect.MakeXYWH(-pw / 2, -ph / 2, pw, 16), paint(band))
        text(c, spec['publisher'].upper(), L, -ph / 2 + 70, 22, 'ib', INK2, align='l', shadow=False)
        text(c, spec.get('kicker', 'RESEARCH'), pw / 2 - 70, -ph / 2 + 70, 20, 'im', INK2, align='r', shadow=False)
        c.drawLine(L, -ph / 2 + 100, pw / 2 - 70, -ph / 2 + 100, paint(0xFFCFC9BC, 1, stroke=2))
        yy = -ph / 2 + 175
        for ln in wrap(spec['title'], 58, 'sb', pw - 140):
            text(c, ln, L, yy, 58, 'sb', INK, align='l', shadow=False); yy += 66
        text(c, spec['subtitle'], L, yy + 6, 28, 'im', INK2, align='l', shadow=False); yy += 70
        _bars(c, L, yy, pw - 140, 4, spec.get('seed', 1)); yy += 4 * 26 + 40
        # data rows
        hp = eo(lin(t, spec.get('hl_t', t0 + 1.5), spec.get('hl_t', t0 + 1.5) + 0.6))
        for i, (lab, val, hot) in enumerate(spec['rows']):
            ry = yy + i * 92
            c.drawLine(L, ry + 44, pw / 2 - 70, ry + 44, paint(0xFFDDD7CA, 1, stroke=1.5))
            vs = 60 if hot else 40
            if hot:
                vw = tw(val, vs, 'gx')
                highlight(c, pw / 2 - 70 - vw, ry, vw, 68, hp)
                highlight(c, L, ry, min(tw(lab, 30, 'ib'), pw - 180 - tw(val, vs, 'gx')), 38, hp, a=0.32)
            lf, ls = ('ib', 30) if hot else ('is', 28)
            room = pw - 140 - tw(val, vs, 'gx') - 40
            while ls > 18 and tw(lab, ls, lf) > room: ls -= 1
            text(c, lab, L, ry, ls, lf, INK if hot else INK2, align='l', shadow=False)
            text(c, val, pw / 2 - 70, ry, vs, 'gx', 0xFFB91C1C if hot else INK, align='r', shadow=False)
        yy += len(spec['rows']) * 92 + 30
        _bars(c, L, yy, pw - 140, max(0, int((ph / 2 - 90 - yy) / 26)), spec.get('seed', 1) + 7)
        if spec.get('foot'):
            text(c, spec['foot'], L, ph / 2 - 50, 20, 'im', INK2, align='l', shadow=False)

# ---------------- headline card ----------------
def _torn(rect, seed, amp=7):
    r = random.Random(seed); p = skia.Path(); x0, y0, x1, y1 = rect.left(), rect.top(), rect.right(), rect.bottom()
    p.moveTo(x0, y0); x = x0
    while x < x1: x = min(x1, x + r.uniform(14, 30)); p.lineTo(x, y0 + r.uniform(-amp, amp))
    y = y0
    while y < y1: y = min(y1, y + r.uniform(14, 30)); p.lineTo(x1 + r.uniform(-amp, amp), y)
    while x > x0: x = max(x0, x - r.uniform(14, 30)); p.lineTo(x, y1 + r.uniform(-amp, amp))
    while y > y0: y = max(y0, y - r.uniform(14, 30)); p.lineTo(x0 + r.uniform(-amp, amp), y)
    p.close(); return p

def headline_card(c, t, t0, outlet, headline, date, x=W / 2, y=H / 2 - 40, t1=None, w=1300, rot0=-3.5, seed=3, hl_words=None):
    a, s, dy = env(t, t0, t1, d=0.6, rise=90)
    if a <= 0.002: return
    hs = 76
    lines = wrap(headline, hs, 'sb', w - 160)
    while len(lines) > 3 and hs > 46: hs -= 4; lines = wrap(headline, hs, 'sb', w - 160)
    lh = hs * 1.16; h = 210 + len(lines) * lh
    rot = lerp(rot0 - 3, rot0, eo(lin(t, t0, t0 + 0.8)))
    with G(c, x, y + dy, a, s * (1 + 0.035 * lin(t, t0, t0 + 6)), rot=rot):
        rect = skia.Rect.MakeXYWH(-w / 2, -h / 2, w, h)
        sh = skia.Paint(AntiAlias=True, Color=0x8C000000, MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 26))
        path = _torn(rect, seed)
        c.save(); c.translate(0, 22); c.drawPath(path, sh); c.restore()
        c.drawPath(path, paint(PAPER))
        L = -w / 2 + 80
        text(c, outlet.upper(), L, -h / 2 + 62, 26, 'ib', 0xFFB91C1C, align='l', shadow=False)
        if date: text(c, date, w / 2 - 80, -h / 2 + 62, 24, 'im', INK2, align='r', shadow=False)
        c.drawLine(L, -h / 2 + 96, w / 2 - 80, -h / 2 + 96, paint(INK, 1, stroke=3))
        hp = eo(lin(t, t0 + 0.9, t0 + 1.6))
        for i, ln in enumerate(lines):
            ly = -h / 2 + 160 + i * lh
            if hp > 0: highlight(c, L, ly + 4, tw(ln, hs, 'sb'), hs * 0.92, clamp(hp * len(lines) - i), a=0.5)
            text(c, ln, L, ly, hs, 'sb', INK, align='l', shadow=False)
        _bars(c, L, h / 2 - 34, w - 160, 1, seed, h=9)

# ---------------- photo card ----------------
def photo_card(c, t, t0, name, x, y, w, h, t1=None, rot=-3, caption=None, credit=None, focus=(0.5, 0.35)):
    a, s, dy = env(t, t0, t1, d=0.6, rise=80)
    if a <= 0.002: return
    img = photo(name)
    with G(c, x, y + dy, a, s, rot=lerp(rot - 4, rot, eo(lin(t, t0, t0 + 0.8)))):
        pad, capb = 22, (78 if caption else 22)
        rect = skia.Rect.MakeXYWH(-w / 2 - pad, -h / 2 - pad, w + 2 * pad, h + pad + capb)
        _shadow(c, rect, r=4, a=0.6)
        c.drawRect(rect, paint(0xFFF7F5F0))
        z = 1.06 + 0.06 * lin(t, t0, t0 + 8)
        sc = max(w / img.width(), h / img.height()) * z
        iw, ih = img.width() * sc, img.height() * sc
        left = clamp(-focus[0] * iw + w / 2, w / 2 - iw, -w / 2) if False else clamp(-iw * focus[0], -iw + w / 2, -w / 2)
        top = clamp(-ih * focus[1], -ih + h / 2, -h / 2)
        c.save(); c.clipRect(skia.Rect.MakeXYWH(-w / 2, -h / 2, w, h))
        c.drawImageRect(img, skia.Rect.MakeXYWH(left, top, iw, ih), skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear),
                        skia.Paint(ColorFilter=skia.ColorFilters.Matrix(_sat_matrix(0.85, 1.0))))
        c.restore()
        if caption: text(c, caption, 0, h / 2 + 40, 34, 'ib', INK, shadow=False)
    if credit:
        text(c, credit, x, y + dy + h / 2 + capb + 40, 18, 'im', C['muted'], a * 0.85, shadow=False)

def tag_chip(c, t, t0, t1, label, x, y, col=None, size=28):
    a, s, dy = env(t, t0, t1, d=0.4, rise=20)
    if a > 0:
        with G(c, x, y + dy, a, s): chip(c, 0, 0, label, col or C['amber'], size, fn='ib')
