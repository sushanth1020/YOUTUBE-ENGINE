"""Click-worthy 1280x720 thumbnails: a real face cut out (with white outline + glow), 2-5 huge words, a number badge.

Face sources: the real person in the story (Wikipedia/Commons, free licence) — or an expressive stock face.
Background removal uses `rembg` when installed (pip install rembg); otherwise the photo is faded into the
background instead of cut out.
"""
import numpy as np, skia
from PIL import Image, ImageFilter, ImageEnhance
from .render.eng import font, tw, _draw, C, paint, rgba
from .util import log

TW, TH = 1280, 720
ACCENT = dict(yellow=0xFFFFD400, amber=0xFFF59E0B, red=0xFFEF4444, green=0xFF22C55E, blue=0xFF60A5FA, white=0xFFFFFFFF)
_session = [None]


def _cutout(path):
    img = Image.open(path).convert('RGB')
    img.thumbnail((1400, 1400))
    try:
        from rembg import remove, new_session
        if _session[0] is None: _session[0] = new_session('u2net')
        out = remove(img, session=_session[0])
        a = np.array(out)[:, :, 3]
        if (a > 128).mean() < 0.04: raise ValueError('cutout too small')
        bbox = out.getbbox()
        return out.crop(bbox), True
    except Exception as e:
        log.info('no cutout (%s); using photo fade', e)
        return img.convert('RGBA'), False


def _to_skia(pil):
    arr = np.ascontiguousarray(np.array(pil.convert('RGBA')))
    return skia.Image.fromarray(arr, colorType=skia.kRGBA_8888_ColorType)


def _outline(rgba, px=10, color=(255, 255, 255)):
    a = rgba.split()[3]
    grown = a.filter(ImageFilter.MaxFilter(px * 2 + 1))
    layer = Image.new('RGBA', rgba.size, color + (0,)); layer.putalpha(grown)
    return layer


def _text(c, s, x, y, size, color, stroke=True):
    f = font('mx', size)
    yb = y + size * 0.36
    sh = skia.Paint(AntiAlias=True, Color=0xD0000000, MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, size * 0.08))
    _draw(c, s, x + size * 0.03, yb + size * 0.07, f, sh)
    if stroke:
        p = skia.Paint(AntiAlias=True, Color=0xFF000000, Style=skia.Paint.kStroke_Style, StrokeWidth=size * 0.09,
                       StrokeJoin=skia.Paint.kRound_Join)
        _draw(c, s, x, yb, f, p)
    _draw(c, s, x, yb, f, paint(color))


def _fit(s, maxw, maxs=190, mins=60):
    size = maxs
    while size > mins and tw(s, size, 'mx') > maxw: size -= 4
    return size


def _bg(c, bg_path, glow_col):
    c.clear(0xFF070C17)
    if bg_path:
        try:
            im = Image.open(bg_path).convert('RGB')
            im = ImageEnhance.Brightness(im.filter(ImageFilter.GaussianBlur(3))).enhance(0.45)
            si = _to_skia(im); sc = max(TW / si.width(), TH / si.height())
            c.drawImageRect(si, skia.Rect.MakeXYWH((TW - si.width() * sc) / 2, (TH - si.height() * sc) / 2, si.width() * sc, si.height() * sc))
        except Exception as e: log.warning('thumb bg failed: %s', e)
    c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeRadial((TW * 0.72, TH * 0.45), 620, [rgba(glow_col, 0.35), rgba(glow_col, 0)])))
    c.drawPaint(skia.Paint(Shader=skia.GradientShader.MakeRadial((TW / 2, TH / 2), 900, [0x00000000, 0xA0000000])))


def _face(c, face_path, side):
    if not face_path: return 0
    cut, ok = _cutout(face_path)
    if ok:
        cut = ImageEnhance.Contrast(ImageEnhance.Color(cut).enhance(1.15)).enhance(1.08)
        h = TH * 1.02; w = cut.width * h / cut.height
        if w > TW * 0.55: w = TW * 0.55; h = cut.height * w / cut.width
        cut = cut.resize((int(w), int(h)), Image.LANCZOS)
        ol = _outline(cut, px=9)
        x = TW - w + 10 if side == 'right' else -10
        y = TH - h + 8
        glow = skia.Paint(ImageFilter=skia.ImageFilters.Blur(30, 30), Alphaf=0.55)
        si, so = _to_skia(cut), _to_skia(ol)
        c.drawImage(so, x, y, skia.SamplingOptions(), glow)
        c.drawImage(so, x, y); c.drawImage(si, x, y)
        return w
    # no cutout: photo on one side with a soft fade into the background
    si = _to_skia(cut); h = TH * 1.05; w = si.width() * h / si.height()
    x = TW - w + 40 if side == 'right' else -40
    c.drawImageRect(si, skia.Rect.MakeXYWH(x, -18, w, h))
    stops = [0xFF070C17, 0xF0070C17, 0x10070C17] if side == 'right' else [0x10070C17, 0xF0070C17, 0xFF070C17]
    pos = [0, 0.42, 0.72] if side == 'right' else [0.28, 0.58, 1.0]
    c.drawRect(skia.Rect.MakeWH(TW, TH), skia.Paint(Shader=skia.GradientShader.MakeLinear([(0, 0), (TW, 0)], stops, pos)))
    return min(w, TW * 0.5)


def render(spec, out_jpg, face_path=None, bg_path=None, side='right'):
    lines = [str(l).upper() for l in spec.get('lines', [])][:3]
    acc_i = int(spec.get('accent', len(lines) - 1) or 0)
    acc = ACCENT.get(str(spec.get('accent_color', 'yellow')).lower(), ACCENT['yellow'])
    s = skia.Surface(TW, TH); c = s.getCanvas()
    _bg(c, bg_path, acc)
    fw = _face(c, face_path, side)
    text_w = (TW - max(fw * 0.92, 380) - 60) if face_path else TW - 120
    text_w = max(text_w, 640)
    x0 = 52 if side == 'right' else TW - text_w - 52
    sizes = [_fit(l, text_w, 200 if len(lines) <= 2 else 165) for l in lines]
    total = sum(sz * 1.02 for sz in sizes)
    badge = spec.get('badge')
    y = (TH - total - (110 if badge else 0)) / 2 + 10
    for i, (l, sz) in enumerate(zip(lines, sizes)):
        _text(c, l, x0, y + sz * 0.5, sz, acc if i == acc_i else C['white'])
        y += sz * 1.02
    if badge:
        b = str(badge); bs = 70; w = tw(b, bs, 'mx') + 60
        bx = x0 + 6; by = y + 20
        bcol = ACCENT.get(str(spec.get('badge_color', 'green')).lower(), ACCENT['green'])
        c.save(); c.rotate(-3, bx + w / 2, by + 55)
        c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(bx, by + 8, w, 110), 16, 16), paint(0xFF000000, 0.6))
        c.drawRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(bx, by, w, 110), 16, 16), paint(bcol))
        _text(c, b, bx + 30, by + 55, bs, 0xFF0B1220, stroke=False)
        c.restore()
    img = s.makeImageSnapshot()
    png = str(out_jpg).rsplit('.', 1)[0] + '.png'
    img.save(png)
    Image.open(png).convert('RGB').save(out_jpg, 'JPEG', quality=90, optimize=True)
    return out_jpg


def make_pair(sb, assets, outdir):
    th = sb['thumbnail']
    face = None
    if th.get('person_wiki'): face = assets.wiki(th['person_wiki'])
    if not face and th.get('face_query'): face = assets.stock_photo(th['face_query'])
    bg = assets.resolve_bg(th.get('bg')) if th.get('bg') else None
    bg_path = None
    if bg and bg[0] == 'p': bg_path = bg[1]
    elif bg and bg[0] == 'v':
        from .util import run
        bg_path = str(outdir / 'thumb_bg.jpg')
        try: run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', '2', '-i', bg[1], '-frames:v', '1', bg_path])
        except Exception: bg_path = None
    a = render(th, outdir / 'thumbnail_A.jpg', face, bg_path, 'right')
    vb = dict(th, **(th.get('variant_b') or {}))
    b = render(vb, outdir / 'thumbnail_B.jpg', face, bg_path, 'left')
    return a, b, face
