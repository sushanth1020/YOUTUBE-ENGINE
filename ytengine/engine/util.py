import json, logging, os, re, sys, time, hashlib
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
CACHE = DATA / 'cache'
RUNS = ROOT / 'runs'
for d in (DATA, CACHE, RUNS): d.mkdir(parents=True, exist_ok=True)

UA = 'YTMoneyEngine/1.0 (personal channel automation; contact: owner)'

log = logging.getLogger('engine')


def setup_logging(logfile=None):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # Windows consoles/redirects default to cp1252
    except Exception: pass
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S')
    log.setLevel(logging.INFO); log.handlers.clear()
    sh = logging.StreamHandler(sys.stdout); sh.setFormatter(fmt); log.addHandler(sh)
    if logfile:
        fh = logging.FileHandler(logfile, encoding='utf-8'); fh.setFormatter(fmt); log.addHandler(fh)
    return log


def sha(s, n=12):
    return hashlib.sha1(str(s).encode('utf-8')).hexdigest()[:n]


def http(method, url, retries=4, backoff=3.0, ok=(200,), budget=90, **kw):
    """requests with retry on 429/5xx (honouring Retry-After) inside a total time budget, so one slow host
    can never stall the daily run. Connection refusals fail fast."""
    headers = kw.pop('headers', {}) or {}
    headers.setdefault('User-Agent', UA)
    timeout = kw.pop('timeout', 60)
    t_start, last = time.time(), None
    for i in range(retries):
        try:
            r = requests.request(method, url, headers=headers, timeout=timeout, **kw)
            if r.status_code in ok: return r
            last = r
            if r.status_code == 429 or r.status_code >= 500:
                wait = min(float(r.headers.get('Retry-After', backoff * (2 ** i)) or 5), 60)
                if time.time() - t_start + wait > budget: break
                log.warning('HTTP %s on %s, retrying in %.0fs', r.status_code, url[:90], wait)
                time.sleep(wait); continue
            r.raise_for_status()
        except (requests.exceptions.ProxyError, requests.exceptions.SSLError) as e:
            last = e; break                                   # blocked host: don't hammer it
        except requests.RequestException as e:
            last = e
            if time.time() - t_start + backoff * (2 ** i) > budget: break
            log.warning('HTTP error %s (%s), retry %d', url[:90], str(e)[:120], i + 1); time.sleep(backoff * (2 ** i))
    if isinstance(last, requests.Response): last.raise_for_status()
    raise RuntimeError(f'HTTP failed: {url[:120]} ({str(last)[:200]})')


def download(url, path, **kw):
    path = Path(path)
    if path.exists() and path.stat().st_size > 0: return path
    r = http('GET', url, stream=True, **kw)
    tmp = path.with_suffix(path.suffix + '.part')
    with open(tmp, 'wb') as f:
        for chunk in r.iter_content(1 << 16): f.write(chunk)
    tmp.replace(path)
    return path


def extract_json(text):
    """Pull the first JSON object out of an LLM reply (handles ```json fences and stray prose)."""
    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.S)
    cand = m.group(1) if m else text
    start = cand.find('{')
    if start < 0: raise ValueError('no JSON object found')
    depth, ins, esc = 0, False, False
    for i in range(start, len(cand)):
        ch = cand[i]
        if ins:
            if esc: esc = False
            elif ch == '\\': esc = True
            elif ch == '"': ins = False
            continue
        if ch == '"': ins = True
        elif ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                raw = cand[start:i + 1]
                try: return json.loads(raw)
                except json.JSONDecodeError:
                    return json.loads(re.sub(r',\s*([}\]])', r'\1', raw))   # trailing commas
    raise ValueError('unterminated JSON object')


def save_json(obj, path):
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding='utf-8')
    return path


def load_json(path, default=None):
    p = Path(path)
    if not p.exists(): return default
    return json.loads(p.read_text(encoding='utf-8'))


def run(cmd, **kw):
    import subprocess
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0: raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-800:]}")
    return r.stdout


def ffprobe_duration(path):
    out = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)])
    return float(out.strip() or 0)
