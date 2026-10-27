"""Channel memory: what was made, when it publishes, which assets were used."""
from datetime import datetime, timedelta, timezone
from .util import DATA, load_json, save_json

PATH = DATA / 'history.json'


def load():
    return load_json(PATH, {'videos': [], 'assets': {}})


def save(h):
    save_json(h, PATH)


def recent(h, days=60):
    cut = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for v in h['videos']:
        try:
            if datetime.fromisoformat(v['created']) >= cut: out.append(v)
        except Exception: out.append(v)
    return out


def slot_taken(h, slot_iso):
    return any(v.get('publish_at') == slot_iso and v.get('status') in ('scheduled', 'uploaded') for v in h['videos'])


def record_video(h, entry):
    h['videos'] = [v for v in h['videos'] if v.get('run_id') != entry.get('run_id')] + [entry]
    save(h)


def mark_assets(h, ids):
    now = datetime.now(timezone.utc).isoformat()
    for i in ids: h['assets'][i] = now
    save(h)


def asset_recent(h, aid, days):
    t = h['assets'].get(aid)
    if not t: return False
    return datetime.fromisoformat(t) > datetime.now(timezone.utc) - timedelta(days=days)


def last_published(h):
    vids = [v for v in h['videos'] if v.get('video_id') and v.get('status') in ('scheduled', 'uploaded')]
    return sorted(vids, key=lambda v: v.get('publish_at', ''))[-1] if vids else None
