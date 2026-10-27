"""One-time: log in to YouTube on your PC and get the token the cloud runner uses.
Needs client_secret.json (Google Cloud > OAuth client > Desktop app) in this folder."""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.force-ssl']
here = Path(__file__).resolve().parent
found = sorted(here.glob('client_secret*.json*'))   # tolerate client_secret.json.json / the long Google file name
if not found:
    raise SystemExit('Put client_secret.json in this folder first (see CLOUD_SETUP.md, step 3).')
print('Using', found[0].name)
creds = InstalledAppFlow.from_client_secrets_file(str(found[0]), SCOPES).run_local_server(
    port=0, prompt='consent', access_type='offline')
(here / 'youtube_token.json').write_text(creds.to_json())
print('\n=== SUCCESS ===\nyoutube_token.json saved and copied to your clipboard.')
print('Paste it into GitHub as the secret YT_TOKEN_JSON. Never share this file.')
