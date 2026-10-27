"""Pre-upload checks — a broken video never goes out."""
import re
from .util import run, ffprobe_duration


def check(video, target_minutes, thumb):
    issues = []
    dur = ffprobe_duration(video)
    if dur < 60: issues.append(f'video too short: {dur:.0f}s')
    if target_minutes:
        if dur < target_minutes * 60 * 0.55: issues.append(f'video too short: {dur / 60:.1f} min vs target {target_minutes}')
        if dur > target_minutes * 60 * 1.7: issues.append(f'video too long: {dur / 60:.1f} min vs target {target_minutes}')
    streams = run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height', '-of', 'csv=p=0', str(video)])
    if 'audio' not in streams: issues.append('no audio stream')
    if '1920,1080' not in streams: issues.append('video is not 1920x1080')
    import subprocess
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(video), '-map', '0:a', '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True)
    m = re.search(r'mean_volume: (-?[\d.]+) dB', r.stderr)
    mean = float(m.group(1)) if m else -99
    if mean < -30: issues.append(f'audio too quiet ({mean} dB)')
    import os
    if not thumb or not os.path.exists(thumb) or os.path.getsize(thumb) > 2_000_000: issues.append('thumbnail missing or > 2MB')
    return dict(ok=not issues, issues=issues, duration=dur, mean_db=mean)


def contact_sheet(video, out_jpg, n=12):
    dur = ffprobe_duration(video)
    fps = max(n / max(dur, 1), 0.001)
    run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(video), '-vf', f'fps={fps:.5f},scale=480:-1,tile=4x3', '-frames:v', '1', str(out_jpg)])
    return out_jpg
