"""YouTube Data API v3: OAuth, resumable upload, scheduled publishing, thumbnail, captions, playlist."""
import time, random
from pathlib import Path
from .util import DATA, ROOT, log

SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.force-ssl']
TOKEN = DATA / 'youtube_token.json'
CLIENT = ROOT / 'client_secret.json'


def authorize(interactive=True):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try: creds.refresh(Request())
        except Exception as e: log.warning('token refresh failed: %s', e); creds = None
    if not creds or not creds.valid:
        if not interactive: raise RuntimeError('YouTube not authorised. Run: python run_daily.py --auth')
        if not CLIENT.exists(): raise RuntimeError(f'Put your OAuth client file at {CLIENT} (see README).')
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
        creds = flow.run_local_server(port=0, prompt='consent', access_type='offline')
    TOKEN.write_text(creds.to_json(), encoding='utf-8')
    return creds


def service(interactive=False):
    from googleapiclient.discovery import build
    return build('youtube', 'v3', credentials=authorize(interactive), cache_discovery=False)


def channel_info(yt):
    r = yt.channels().list(part='snippet,statistics', mine=True).execute()
    it = (r.get('items') or [{}])[0]
    return dict(id=it.get('id'), title=it.get('snippet', {}).get('title'), subs=it.get('statistics', {}).get('subscriberCount'))


def _resumable(req):
    from googleapiclient.errors import HttpError
    resp, retry = None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status: log.info('upload %d%%', int(status.progress() * 100))
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < 8:
                retry += 1; time.sleep(min(60, 2 ** retry + random.random())); continue
            raise
        except (ConnectionError, TimeoutError, OSError) as e:
            if retry < 8: retry += 1; log.warning('upload network error %s, retrying', e); time.sleep(min(60, 2 ** retry)); continue
            raise
    return resp


def upload(yt, video, meta, publish_at_utc_iso, ucfg):
    from googleapiclient.http import MediaFileUpload
    body = {
        'snippet': {'title': meta['title'][:100], 'description': meta['description'][:4900], 'tags': meta['tags'],
                    'categoryId': str(ucfg.get('category_id', '27')),
                    'defaultLanguage': ucfg.get('default_language', 'en'), 'defaultAudioLanguage': ucfg.get('default_language', 'en')},
        'status': {'privacyStatus': 'private', 'publishAt': publish_at_utc_iso,
                   'selfDeclaredMadeForKids': bool(ucfg.get('made_for_kids', False)),
                   'containsSyntheticMedia': bool(ucfg.get('disclose_synthetic_media', True)),
                   'embeddable': True, 'license': 'youtube'},
    }
    media = MediaFileUpload(str(video), mimetype='video/mp4', chunksize=16 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part='snippet,status', body=body, media_body=media,
                             notifySubscribers=bool(ucfg.get('notify_subscribers', True)))
    resp = _resumable(req)
    log.info('uploaded video id %s (scheduled %s)', resp['id'], publish_at_utc_iso)
    return resp['id']


def set_thumbnail(yt, vid, jpg):
    from googleapiclient.http import MediaFileUpload
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(jpg), mimetype='image/jpeg')).execute(); return True
    except Exception as e:
        log.error('thumbnail upload failed (channel must be phone-verified for custom thumbnails): %s', e); return False


def upload_captions(yt, vid, srt, lang='en'):
    from googleapiclient.http import MediaFileUpload
    try:
        yt.captions().insert(part='snippet', body={'snippet': {'videoId': vid, 'language': lang, 'name': 'English', 'isDraft': False}},
                             media_body=MediaFileUpload(str(srt), mimetype='application/octet-stream')).execute(); return True
    except Exception as e:
        log.error('caption upload failed: %s', e); return False


def ensure_playlist(yt, title):
    r = yt.playlists().list(part='snippet', mine=True, maxResults=50).execute()
    for p in r.get('items', []):
        if p['snippet']['title'] == title: return p['id']
    p = yt.playlists().insert(part='snippet,status', body={'snippet': {'title': title}, 'status': {'privacyStatus': 'public'}}).execute()
    return p['id']


def add_to_playlist(yt, vid, title):
    try:
        pid = ensure_playlist(yt, title)
        yt.playlistItems().insert(part='snippet', body={'snippet': {'playlistId': pid, 'resourceId': {'kind': 'youtube#video', 'videoId': vid}}}).execute()
        return True
    except Exception as e:
        log.warning('playlist add failed: %s', e); return False


def video_status(yt, vid):
    r = yt.videos().list(part='status,processingDetails', id=vid).execute()
    return (r.get('items') or [{}])[0]
