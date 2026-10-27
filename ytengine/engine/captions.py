"""Caption chunking (shared by burned-in captions and the uploaded .srt)."""
import re

MAX_CHARS = 64      # ~2 short lines on screen
NUM_RE = re.compile(r"^[\(\[]?[₹$€£]?\d[\d,\.]*(%|x|X|K|M|B|Cr|L|k)?[\)\]]?$")


def chunk_words(words, max_chars=MAX_CHARS):
    """words: [{'w','s','e'}] -> [{'s','e','words':[...]}]. Breaks at sentence ends and at max_chars."""
    chunks, cur, n = [], [], 0
    for w in words:
        ln = len(w['w']) + 1
        if cur and (n + ln > max_chars):
            chunks.append(cur); cur, n = [], 0
        cur.append(w); n += ln
        if w['w'].endswith(('.', '?', '!')) and n > 18:
            chunks.append(cur); cur, n = [], 0
    if cur: chunks.append(cur)
    return [{'s': c[0]['s'], 'e': c[-1]['e'], 'words': c} for c in chunks]


def _ts(t):
    t = max(0.0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f'{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}'


def write_srt(sections, path):
    """sections: [{'offset': abs start of voice, 'words': [...]}]"""
    cues = []
    for sec in sections:
        for ch in chunk_words(sec['words']):
            cues.append([sec['offset'] + ch['s'], sec['offset'] + max(ch['e'], ch['s'] + 0.6) + 0.15, ' '.join(w['w'] for w in ch['words'])])
    for i in range(len(cues) - 1):
        cues[i][1] = min(cues[i][1], cues[i + 1][0] - 0.01)      # no overlapping cues
    out = [f"{k}\n{_ts(s)} --> {_ts(e)}\n{txt}\n" for k, (s, e, txt) in enumerate(cues, 1)]
    with open(path, 'w', encoding='utf-8') as f: f.write('\n'.join(out))
    return path
