"""Cheap checks that run BEFORE any Claude call, so a bad key fails in seconds instead of after
the expensive research + script stage has already used your Claude usage."""
import requests
from .config import env
from .util import log


class PreflightError(RuntimeError):
    pass


def _body(r):
    try: return str(r.json())[:400]
    except Exception: return (r.text or '')[:400]


def elevenlabs(vcfg):
    key = (env('ELEVENLABS_API_KEY') or '').strip()
    if not key: raise PreflightError('ELEVENLABS_API_KEY is missing (GitHub: Settings > Secrets and variables > Actions)')
    e = vcfg['elevenlabs']
    # A real 2-character synthesis: proves the key, its Text-to-Speech permission, the voice and the plan all work.
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{e['voice_id']}?output_format=mp3_22050_32",
                      headers={'xi-api-key': key, 'Content-Type': 'application/json'},
                      json=dict(text='Hi', model_id=e.get('model_id', 'eleven_multilingual_v2')), timeout=60)
    if r.status_code != 200:
        hint = {401: 'the key is wrong, restricted (needs Text to Speech permission), or ElevenLabs blocked the free plan from cloud servers',
                402: 'out of ElevenLabs credits / plan limit',
                404: f"voice_id {e['voice_id']} not found in your ElevenLabs account"}.get(r.status_code, 'see the message above')
        raise PreflightError(f'ElevenLabs check failed (HTTP {r.status_code}): {_body(r)} -> {hint}')
    log.info('preflight: ElevenLabs OK')


def pixabay():
    key = (env('PIXABAY_API_KEY') or '').strip()
    if not key: raise PreflightError('PIXABAY_API_KEY is missing')
    r = requests.get('https://pixabay.com/api/', params=dict(key=key, q='money', per_page=3), timeout=30)
    if r.status_code != 200:
        raise PreflightError(f'Pixabay check failed (HTTP {r.status_code}): {_body(r)} -> the key is wrong')
    log.info('preflight: Pixabay OK')


def run(cfg):
    errors = []
    checks = [pixabay]
    if cfg['voice'].get('provider', 'elevenlabs') == 'elevenlabs':
        checks.insert(0, lambda: elevenlabs(cfg['voice']))
    for c in checks:
        try: c()
        except PreflightError as e: errors.append(str(e))
        except requests.RequestException as e: log.warning('preflight: could not reach a service (%s) — continuing', e)
    if errors:
        raise PreflightError('Stopped before using any Claude usage:\n- ' + '\n- '.join(errors))
