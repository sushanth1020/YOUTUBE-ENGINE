"""Voiceover: ElevenLabs (human-sounding, expressive) with exact word timings, plus a free local fallback.

Each section is synthesised in one request (natural flow between sentences), with previous/next text
passed for continuity across sections. ElevenLabs returns per-character timing, which we turn into
sentence windows (for visual beats) and word windows (for karaoke captions + the uploaded .srt).
"""
import base64, json, re
from pathlib import Path
import numpy as np
from .util import http, run, log, save_json, load_json
from .config import env

SR = 48000
MAX_CHARS = 2400   # per request; long sections are split on sentence boundaries


def _to_wav(src, dst):
    run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(src), '-ac', '1', '-ar', str(SR), str(dst)])
    return dst


def _words_from_alignment(text, al, t_off=0.0):
    chars, st, en = al['characters'], al['character_start_times_seconds'], al['character_end_times_seconds']
    joined = ''.join(chars)
    if joined != text:  # alignment on normalised text; fall back to proportional mapping
        log.warning('alignment text mismatch; using proportional word timing')
        return None
    words, i = [], 0
    for m in re.finditer(r'\S+', text):
        a, b = m.start(), m.end() - 1
        words.append({'w': m.group(), 's': st[a] + t_off, 'e': en[b] + t_off, 'c0': m.start(), 'c1': m.end()})
    return words


def _proportional_words(sent_windows):
    words = []
    for sw in sent_windows:
        toks = sw['text'].split(); total = sum(len(t) + 1 for t in toks) or 1
        t = sw['start']; dur = sw['end'] - sw['start']
        for tok in toks:
            d = dur * (len(tok) + 1) / total
            words.append({'w': tok, 's': t, 'e': t + d}); t += d
    return words


def _chunks(sentences):
    out, cur = [], []
    for s in sentences:
        if cur and len(' '.join(cur + [s])) > MAX_CHARS: out.append(cur); cur = []
        cur.append(s)
    if cur: out.append(cur)
    return out


def elevenlabs_section(sentences, out_wav, vcfg, prev_text='', next_text=''):
    key = env('ELEVENLABS_API_KEY', required=True)
    e = vcfg['elevenlabs']
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{e['voice_id']}/with-timestamps?output_format=mp3_44100_128"
    audio_parts, words, segs, t_off = [], [], [], 0.0
    chunks = _chunks(sentences)
    for ci, ch in enumerate(chunks):
        text = ' '.join(ch)
        body = dict(text=text, model_id=e.get('model_id', 'eleven_multilingual_v2'), apply_text_normalization='auto',
                    voice_settings=dict(stability=e.get('stability', 0.4), similarity_boost=e.get('similarity_boost', 0.8),
                                        style=e.get('style', 0.3), use_speaker_boost=e.get('use_speaker_boost', True),
                                        speed=e.get('speed', 1.0)),
                    previous_text=(prev_text if ci == 0 else ' '.join(chunks[ci - 1]))[-600:] or None,
                    next_text=(next_text if ci == len(chunks) - 1 else ' '.join(chunks[ci + 1]))[:600] or None)
        r = http('POST', url, headers={'xi-api-key': key, 'Content-Type': 'application/json'}, json=body, timeout=180)
        js = r.json()
        mp3 = Path(str(out_wav) + f'.{ci}.mp3'); mp3.write_bytes(base64.b64decode(js['audio_base64']))
        part = Path(str(out_wav) + f'.{ci}.wav'); _to_wav(mp3, part); mp3.unlink(missing_ok=True)
        import soundfile as sf
        a, _ = sf.read(str(part), dtype='float32'); part.unlink(missing_ok=True)
        al = js.get('alignment') or js.get('normalized_alignment')
        ws = _words_from_alignment(text, al, t_off) if al else None
        # sentence windows from character offsets
        pos = 0
        for s in ch:
            c0 = text.find(s, pos); c1 = c0 + len(s); pos = c1
            if ws:
                inside = [w for w in ws if w['c0'] >= c0 and w['c1'] <= c1 + 1]
                if inside: segs.append({'text': s, 'start': inside[0]['s'], 'end': inside[-1]['e']}); continue
            # proportional fallback inside this chunk
            frac0, frac1 = c0 / max(1, len(text)), c1 / max(1, len(text))
            segs.append({'text': s, 'start': t_off + frac0 * len(a) / SR, 'end': t_off + frac1 * len(a) / SR})
        if ws: words += [{'w': w['w'], 's': w['s'], 'e': w['e']} for w in ws]
        audio_parts.append(a); t_off += len(a) / SR
        gap = np.zeros(int(0.25 * SR), np.float32); audio_parts.append(gap); t_off += 0.25
    audio = np.concatenate(audio_parts)
    if not words: words = _proportional_words(segs)
    return audio, segs, words


def kokoro_section(sentences, out_wav, vcfg):
    """Free local voice (robotic compared to ElevenLabs). Used as fallback / for tests."""
    from kokoro_onnx import Kokoro
    from .util import DATA
    k = Kokoro(env('KOKORO_MODEL', str(DATA / 'kokoro' / 'kokoro.onnx')), env('KOKORO_VOICES', str(DATA / 'kokoro' / 'voices.bin')))
    kc = vcfg.get('kokoro', {})
    parts, segs, t = [], [], 0.0
    import scipy.signal as sps
    for s in sentences:
        a, sr = k.create(s, voice=kc.get('voice', 'am_michael'), speed=kc.get('speed', 0.92), lang='en-us')
        idx = np.where(np.abs(a) > 0.01)[0]
        if len(idx): a = a[max(0, idx[0] - 240):idx[-1] + 480]
        a = sps.resample_poly(a, SR, sr).astype(np.float32)
        segs.append({'text': s, 'start': t, 'end': t + len(a) / SR})
        gap = 0.42 if s.endswith(('.', '!', '?')) else 0.25
        parts += [a, np.zeros(int(gap * SR), np.float32)]; t += len(a) / SR + gap
    return np.concatenate(parts), segs, _proportional_words(segs)


def synthesize(storyboard, workdir, vcfg):
    """-> list of {wav, dur, segs, words} per section (cached in workdir/voice)."""
    import soundfile as sf
    vdir = Path(workdir) / 'voice'; vdir.mkdir(parents=True, exist_ok=True)
    secs = storyboard['sections']; out = []
    provider = vcfg.get('provider', 'elevenlabs')
    for i, sec in enumerate(secs):
        wav, meta = vdir / f'sec{i:02d}.wav', vdir / f'sec{i:02d}.json'
        cached = load_json(meta)
        if cached and wav.exists() and cached.get('sentences') == sec['sentences']:
            out.append(cached); continue
        prev_t = ' '.join(secs[i - 1]['sentences'][-2:]) if i > 0 else ''
        next_t = ' '.join(secs[i + 1]['sentences'][:2]) if i + 1 < len(secs) else ''
        try:
            if provider == 'kokoro': audio, segs, words = kokoro_section(sec['sentences'], wav, vcfg)
            else: audio, segs, words = elevenlabs_section(sec['sentences'], wav, vcfg, prev_t, next_t)
        except Exception as e:
            if vcfg.get('fallback') == 'kokoro' and provider != 'kokoro':
                log.error('ElevenLabs failed (%s) — falling back to local voice', e)
                audio, segs, words = kokoro_section(sec['sentences'], wav, vcfg)
            else: raise
        sf.write(str(wav), audio, SR)
        rec = dict(wav=str(wav), dur=round(len(audio) / SR, 3), segs=segs, words=words, sentences=sec['sentences'])
        save_json(rec, meta); out.append(rec)
        log.info('voice section %d: %.1fs, %d words', i, rec['dur'], len(words))
    return out


def char_count(storyboard):
    return sum(len(' '.join(s['sentences'])) for s in storyboard['sections'])
