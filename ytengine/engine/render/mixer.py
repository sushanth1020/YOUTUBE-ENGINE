"""Final soundtrack: voice + music bed (ducked under speech) + soft whooshes on chapter changes."""
import random
from pathlib import Path
import numpy as np
import soundfile as sf
from ..util import run, ROOT, log

SR = 48000


def _load_music(path, n):
    tmp = Path(str(path) + '.tmp.wav')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(path), '-ac', '1', '-ar', str(SR), str(tmp)])
    a, _ = sf.read(str(tmp), dtype='float32'); tmp.unlink(missing_ok=True)
    if len(a) == 0: return None
    reps = int(np.ceil(n / len(a))) + 1
    a = np.tile(a, reps)[:n]
    return a / (np.abs(a).max() + 1e-6)


def _synth_pad(n, seed):
    """Fallback ambient bed (Am–F–C–G) if no royalty-free music is provided in /music."""
    tt = np.arange(n) / SR; m = np.zeros(n, np.float32)
    chords = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [130.81, 196.0, 261.63], [196.0, 246.94, 293.66]]
    cl = 4.0
    for k in range(int(n / SR / cl) + 2):
        s0 = int(k * cl * SR); s1 = min(n, int((k + 1) * cl * SR + SR))
        if s0 >= n: break
        seg = tt[s0:s1] - k * cl; envl = np.clip(seg / 1.2, 0, 1) * np.clip((cl + 1 - seg) / 1.2, 0, 1)
        for f in chords[k % 4]:
            for h, amp in ((1, 1), (2, 0.3), (3, 0.12)):
                m[s0:s1] += (amp * np.sin(2 * np.pi * f * h * tt[s0:s1]) * envl).astype(np.float32)
        m[s0:s1] += (0.6 * np.sin(2 * np.pi * chords[k % 4][0] / 2 * tt[s0:s1]) * envl).astype(np.float32)
    m *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.05 * tt) ** 2
    return m / (np.abs(m).max() + 1e-6)


def mix(parts, total, out_wav, seed=0, music_dir=None):
    """parts: [{'start': section start (s), 'lead': voice offset in section, 'wav': path}]"""
    n = int(total * SR) + SR
    voice = np.zeros(n, np.float32)
    for p in parts:
        a, sr = sf.read(p['wav'], dtype='float32')
        if a.ndim > 1: a = a.mean(1)
        i = int((p['start'] + p['lead']) * SR); voice[i:i + len(a)] += a[:max(0, n - i)]
    # music
    mdir = Path(music_dir or ROOT / 'music')
    tracks = sorted([f for f in mdir.glob('*') if f.suffix.lower() in ('.mp3', '.wav', '.m4a', '.ogg', '.flac')])
    music = None
    if tracks:
        pick = random.Random(seed).choice(tracks)
        try: music = _load_music(pick, n); log.info('music: %s', pick.name)
        except Exception as e: log.warning('music load failed: %s', e)
    if music is None: music = _synth_pad(n, seed)
    win = int(0.25 * SR); venv = np.convolve(np.abs(voice), np.ones(win) / win, 'same')
    duck = np.where(venv > 0.01, 0.06 if tracks else 0.045, 0.14 if tracks else 0.11).astype(np.float32)
    duck = np.convolve(duck, np.ones(int(0.4 * SR)) / (0.4 * SR), 'same').astype(np.float32)
    music *= duck
    fade = int(2 * SR); music[-fade:] *= np.linspace(1, 0, fade)
    # whooshes at chapter boundaries
    rng = np.random.default_rng(seed); wh = np.zeros(n, np.float32)
    for p in parts[1:]:
        L = int(0.7 * SR); noise = rng.standard_normal(L).astype(np.float32)
        cs = np.cumsum(np.concatenate([[0], noise])); o = np.zeros(L, np.float32)
        for j in range(0, L):
            w = int(40 - 35 * np.sin(np.pi * j / L)); a0 = max(0, j - w); o[j] = (cs[j + 1] - cs[a0]) / (j + 1 - a0)
        envl = np.sin(np.pi * np.arange(L) / L) ** 2
        i = int(max(0, p['start'] - 0.25) * SR); seg = wh[i:i + L]; wh[i:i + L] += (o * envl)[:len(seg)] * 0.5
    out = voice + music + wh
    out /= max(1.0, np.abs(out).max() / 0.95)
    sf.write(str(out_wav), out[:int(total * SR)], SR)
    return out_wav
