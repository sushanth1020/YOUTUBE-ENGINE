"""Runs at the start of every cloud run: turns GitHub Secrets into the files the engine expects."""
import os, sys, json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
(root / 'data').mkdir(exist_ok=True)
missing = [k for k in ('YT_TOKEN_JSON', 'ELEVENLABS_API_KEY', 'PIXABAY_API_KEY') if not os.environ.get(k)]
if not (os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('CLAUDE_CODE_OAUTH_TOKEN')):
    missing.append('ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN')
if missing:
    print('Missing GitHub secrets:', ', '.join(missing), '- add them in Settings > Secrets and variables > Actions'); sys.exit(1)
tok = json.loads(os.environ['YT_TOKEN_JSON'])
if not tok.get('refresh_token'):
    print('YT_TOKEN_JSON has no refresh_token - re-run connect_youtube.bat and paste the full text'); sys.exit(1)
(root / 'data' / 'youtube_token.json').write_text(json.dumps(tok))
print('credentials ready')
