"""YT Money Engine — daily entry point.

  python run_daily.py                 make + upload the next scheduled video (what the daily task runs)
  python run_daily.py --auth          one-time: connect your YouTube channel (opens a browser)
  python run_daily.py --check         verify keys, ffmpeg, YouTube connection
  python run_daily.py --no-upload     make the video but don't upload (lands in runs/<date>/final.mp4)
  python run_daily.py --preview       research + script + voice, then render a few stills per section only
  python run_daily.py --storyboard samples/demo_storyboard.json --no-upload   render a hand-written storyboard
  Options: --format top_list  --minutes 10  --slot "2026-11-02 18:30"
"""
import argparse, shutil, sys


def main():
    ap = argparse.ArgumentParser(description='Daily faceless finance video engine')
    ap.add_argument('--auth', action='store_true'); ap.add_argument('--check', action='store_true')
    ap.add_argument('--no-upload', action='store_true'); ap.add_argument('--preview', action='store_true')
    ap.add_argument('--storyboard'); ap.add_argument('--format'); ap.add_argument('--minutes', type=int)
    ap.add_argument('--slot', help='"YYYY-MM-DD HH:MM" in the configured timezone')
    ap.add_argument('--config')
    a = ap.parse_args()
    from engine import config
    from engine.util import setup_logging, log
    setup_logging()
    cfg = config.load(a.config)

    if a.auth:
        from engine import youtube
        youtube.authorize(interactive=True)
        info = youtube.channel_info(youtube.service())
        print(f"Connected to YouTube channel: {info['title']} ({info['subs']} subscribers)"); return

    if a.check:
        ok = True
        for k in ('ANTHROPIC_API_KEY', 'ELEVENLABS_API_KEY', 'PIXABAY_API_KEY'):
            v = config.env(k); print(f"{'OK ' if v else 'MISSING'}  {k}"); ok &= bool(v)
        for k in ('PEXELS_API_KEY', 'SMTP_USER', 'SMTP_PASS'):
            print(f"{'OK ' if config.env(k) else 'optional'}  {k}")
        print(f"{'OK ' if shutil.which('ffmpeg') else 'MISSING'}  ffmpeg"); ok &= bool(shutil.which('ffmpeg'))
        try:
            from engine import youtube
            info = youtube.channel_info(youtube.service()); print(f"OK   YouTube: {info['title']}")
        except Exception as e: print(f'MISSING  YouTube connection ({e})'); ok = False
        try:
            import rembg  # noqa
            print('OK   rembg (face cut-outs for thumbnails)')
        except Exception: print('optional  rembg not installed (thumbnails use photo-fade instead of cut-out)')
        from engine import pipeline, history
        print('Next publish slot:', pipeline.next_slot(cfg, history.load()).strftime('%a %d %b %Y %H:%M'))
        sys.exit(0 if ok else 1)

    from engine import pipeline
    from engine.llm import LLM
    res = pipeline.main(cfg, a, lambda: LLM(cfg))
    log.info('result: %s', res)


if __name__ == '__main__':   # required on Windows (multiprocessing uses spawn)
    main()
