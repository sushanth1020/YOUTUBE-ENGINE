"""One daily run: slot -> topic -> storyboard -> assets -> voice -> render -> mix -> thumbnail -> QA -> upload -> notify.

Every stage writes its output into runs/<slot-date>/ and is skipped if already done, so a crash, a reboot or a
sleeping laptop just resumes on the next run.
"""
import json, math, os, random, time, traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from multiprocessing import get_context

from .util import RUNS, log, save_json, load_json, run, sha, setup_logging, ffprobe_duration
from . import history, storyboard as SB, voice as VO, seo, qa, notify
from .assets import Assets
from .render.timeline import render_section, CHAPTER_LEAD, TAIL
from .render import mixer
from .captions import write_srt

DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']


class QueueFull(Exception):
    pass


class Lock:
    """Prevents two runs at once (e.g. the daily trigger and the log-on trigger firing together)."""
    def __init__(self):
        from .util import DATA
        self.p = DATA / 'run.lock'
    def __enter__(self):
        if self.p.exists() and time.time() - self.p.stat().st_mtime < 6 * 3600:
            raise QueueFull('another run is in progress (data/run.lock) — exiting')
        self.p.write_text(str(os.getpid())); return self
    def __exit__(self, *e):
        self.p.unlink(missing_ok=True)


# ------------------------------------------------------------------ scheduling
def next_slot(cfg, hist, now=None, forced=None):
    tz = ZoneInfo(cfg['schedule'].get('timezone', 'Asia/Kolkata'))
    if forced:
        return datetime.strptime(forced, '%Y-%m-%d %H:%M').replace(tzinfo=tz)
    now = now or datetime.now(tz)
    lead = timedelta(minutes=int(cfg['schedule'].get('min_lead_minutes', 45)))
    for d in range(0, 8):
        day = (now + timedelta(days=d)).date()
        hh, mm = map(int, cfg['schedule']['publish_times'][DAYS[day.weekday()]].split(':'))
        slot = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
        if slot - now < lead: continue
        if history.slot_taken(hist, slot.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')): continue
        return slot
    raise RuntimeError('no free publish slot in the next 7 days')


def choose_format(cfg, hist, seed, forced_fmt=None, forced_min=None):
    fm = cfg['content']['formats']; rng = random.Random(seed)
    recent = [v.get('format') for v in sorted(hist['videos'], key=lambda v: v.get('created', ''))[-2:]]
    if forced_fmt: fmt = forced_fmt
    else:
        pool = [(k, v['weight']) for k, v in fm.items() if k not in recent] or list((k, v['weight']) for k, v in fm.items())
        fmt = rng.choices([k for k, _ in pool], weights=[w for _, w in pool])[0]
    lo, hi = fm[fmt]['minutes']
    minutes = forced_min or rng.choice([m for m in (5, 8, 10, 12) if lo <= m <= hi] or [lo])
    return fmt, int(minutes)


# ------------------------------------------------------------------ main run
class Run:
    def __init__(self, cfg, args):
        self.cfg, self.args = cfg, args
        self.hist = history.load()
        tz = ZoneInfo(cfg['schedule'].get('timezone', 'Asia/Kolkata'))
        self.slot = next_slot(cfg, self.hist, forced=getattr(args, 'slot', None))
        ahead = int(cfg['schedule'].get('queue_ahead_days', 1))
        if not getattr(args, 'slot', None) and self.slot.date() > (datetime.now(tz) + timedelta(days=ahead)).date():
            raise QueueFull(f"videos already scheduled through {self.slot.date() - timedelta(days=1)} — nothing to do")
        self.slot_utc = self.slot.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.run_id = self.slot.strftime('%Y-%m-%d_%H%M')
        self.dir = RUNS / self.run_id; self.dir.mkdir(parents=True, exist_ok=True)
        setup_logging(self.dir / 'run.log')
        self.state = load_json(self.dir / 'state.json', {})
        log.info('=== run %s  (publishes %s %s) ===', self.run_id, self.slot.strftime('%a %d %b %H:%M'), tz.key)

    def mark(self, k, v=True):
        self.state[k] = v; save_json(self.state, self.dir / 'state.json')

    # -------------------------------------------------- stages
    def stage_storyboard(self, llm_factory, yt):
        p = self.dir / 'storyboard.json'
        if p.exists(): return load_json(p)
        if getattr(self.args, 'storyboard', None):
            sb = SB.normalize(json.loads(Path(self.args.storyboard).read_text(encoding='utf-8')))
            sb.setdefault('_meta', dict(format='manual', minutes=self.args.minutes))
            save_json(sb, p); return sb
        from . import research
        from .writer import make_storyboard
        fmt, minutes = choose_format(self.cfg, self.hist, self.run_id, self.args.format, self.args.minutes)
        log.info('format: %s, %d min', fmt, minutes)
        news, ytsig = research.gather(self.cfg, yt)
        n, y = research.format_signals(news, ytsig)
        rec = history.recent(self.hist, self.cfg['content'].get('avoid_repeat_days', 60))
        recent = '\n'.join(f"- {v.get('created', '')[:10]} [{v.get('format')}] {v.get('title')} — {v.get('topic', '')}" for v in rec[-40:]) or '- (none yet)'
        last = history.last_published(self.hist)
        watch_next = f'"{last["title"]}"' if last else None
        ctx = dict(today=datetime.now().strftime('%A %d %B %Y'), format=fmt, format_note=self.cfg['content']['formats'][fmt]['note'],
                   minutes=minutes, slot_local=self.slot.strftime('%a %d %b, %H:%M'), recent=recent, news=n, yt=y)
        llm = llm_factory()
        brief, sb = make_storyboard(llm, self.cfg, ctx, fmt, minutes, watch_next)
        save_json(brief, self.dir / 'research_brief.json'); save_json(sb, p)
        save_json(llm.usage, self.dir / 'llm_usage.json')
        log.info('LLM usage: %s', llm.usage)
        return sb

    def stage_assets(self, sb, assets):
        p = self.dir / 'storyboard_resolved.json'
        if p.exists(): return load_json(p)
        sb = assets.resolve_storyboard(sb)
        sb['_credits'] = assets.credit_lines(); sb['_assets_used'] = assets.used
        save_json(sb, p); return sb

    def stage_render(self, sb, timings):
        last = history.last_published(self.hist)
        next_thumb = last.get('thumb') if last and last.get('thumb') and os.path.exists(last.get('thumb')) else None
        jobs = []
        for i, (sec, tm) in enumerate(zip(sb['sections'], timings)):
            lead = 0.0 if i == 0 else CHAPTER_LEAD
            if i == len(sb['sections']) - 1:
                for b in sec['beats']:
                    if b['type'] == 'end': b['_next_thumb'] = next_thumb
            out = self.dir / f'sec{i:02d}.mp4'
            key = sha(json.dumps([sec, tm['segs']], sort_keys=True, default=str))
            done = self.state.get(f'sec{i}') == key and out.exists()
            jobs.append(dict(i=i, key=key, done=done, sec=sec, timing=tm, lead=lead, chapter_no=i, out=str(out),
                             burn_captions=self.cfg['render'].get('burn_captions', True), grain=self.cfg['render'].get('film_grain', True),
                             crf=self.cfg['render'].get('crf', 19), preset=self.cfg['render'].get('preset', 'veryfast')))
        todo = [j for j in jobs if not j['done']]
        workers = int(os.environ.get('RENDER_WORKERS') or self.cfg['render'].get('workers') or 0) or max(1, (os.cpu_count() or 2) - 1)
        if todo:
            log.info('rendering %d sections on %d workers', len(todo), workers)
            todo.sort(key=lambda j: -j['timing']['dur'])
            t0 = time.time()
            with get_context('spawn').Pool(min(workers, len(todo))) as pool:
                for j, res in zip(todo, pool.imap(render_section, todo)):
                    log.info('section %d rendered: %s', j['i'], res)
            for j in todo: self.mark(f"sec{j['i']}", j['key'])
            log.info('render time %.1f min', (time.time() - t0) / 60)
        durs = [ffprobe_duration(j['out']) for j in jobs]
        return jobs, durs

    def stage_final(self, jobs, durs, timings):
        final = self.dir / 'final.mp4'
        starts = [sum(durs[:i]) for i in range(len(durs))]
        if final.exists() and self.state.get('final'): return final, starts
        parts = [dict(start=st, lead=j['lead'], wav=tm['wav']) for st, j, tm in zip(starts, jobs, timings)]
        mix = self.dir / 'mix.wav'
        mixer.mix(parts, sum(durs), mix, seed=int(sha(self.run_id, 6), 16))
        lst = self.dir / 'concat.txt'
        lst.write_text(''.join(f"file '{Path(j['out']).resolve().as_posix()}'\n" for j in jobs), encoding='utf-8')
        run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), '-i', str(mix),
             '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-ac', '2', '-ar', '48000',
             '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(final)])
        self.mark('final'); return final, starts

    # -------------------------------------------------- orchestrate
    def execute(self, llm_factory):
        a, cfg = self.args, self.cfg
        yt = None
        want_upload = cfg['upload'].get('enabled', True) and not a.no_upload
        if want_upload or not a.storyboard:
            try:
                from . import youtube
                yt = youtube.service(interactive=False)
            except Exception as e:
                if want_upload: raise
                log.warning('YouTube not connected (%s) — continuing without YouTube research', e)
        sb = self.stage_storyboard(llm_factory, yt)
        meta = sb.get('_meta', {})
        log.info('title: %s | %d words', sb['title'], SB.word_count(sb))
        assets = Assets(cfg, self.hist)
        sb = self.stage_assets(sb, assets)
        timings = VO.synthesize(sb, self.dir, cfg['voice'])
        if a.preview:
            return self.preview(sb, timings)
        jobs, durs = self.stage_render(sb, timings)
        final, starts = self.stage_final(jobs, durs, timings)
        srt = write_srt([dict(offset=st + j['lead'], words=tm['words']) for st, j, tm in zip(starts, jobs, timings)], self.dir / 'captions.srt')
        from . import thumbnail
        tA, tB, face = thumbnail.make_pair(sb, assets, self.dir) if not self.state.get('thumbs') else (self.dir / 'thumbnail_A.jpg', self.dir / 'thumbnail_B.jpg', None)
        self.mark('thumbs')
        last = history.last_published(self.hist)
        md = seo.build(sb, [st + 0 for st in starts], last, sb.get('_credits', []), cfg)
        save_json(md, self.dir / 'metadata.json')
        (self.dir / 'pinned_comment.txt').write_text(sb.get('pinned_comment', ''), encoding='utf-8')
        report = qa.check(final, meta.get('minutes', 8), str(tA))
        sheet = qa.contact_sheet(final, self.dir / 'contact_sheet.jpg')
        save_json(report, self.dir / 'qa.json')
        entry = dict(run_id=self.run_id, created=datetime.now(timezone.utc).isoformat(), publish_at=self.slot_utc,
                     title=md['title'], topic=meta.get('topic'), format=meta.get('format'), minutes=round(report['duration'] / 60, 1),
                     thumb=str(Path(tA).resolve()), people=meta.get('people'), status='rendered')
        if not report['ok']:
            history.record_video(self.hist, dict(entry, status='qa_failed'))
            raise RuntimeError('QA failed: ' + '; '.join(report['issues']))
        if not want_upload:
            history.record_video(self.hist, entry)
            log.info('upload disabled — video ready at %s', final)
            return dict(entry, video=str(final))
        from . import youtube
        vid = self.state.get('video_id')
        if not vid:
            vid = youtube.upload(yt, final, md, self.slot_utc, cfg['upload']); self.mark('video_id', vid)
        if not self.state.get('thumb_set'): self.mark('thumb_set', youtube.set_thumbnail(yt, vid, tA))
        if cfg['upload'].get('upload_captions', True) and not self.state.get('captions'):
            self.mark('captions', youtube.upload_captions(yt, vid, srt))
        if not self.state.get('playlist'): self.mark('playlist', youtube.add_to_playlist(yt, vid, cfg['upload'].get('playlist_title', 'Uploads')))
        entry.update(video_id=vid, status='scheduled')
        history.record_video(self.hist, entry)
        history.mark_assets(self.hist, sb.get('_assets_used', []))
        local = self.slot.strftime('%a %d %b %Y, %I:%M %p IST')
        notify.send(cfg, f'✅ Scheduled: {md["title"]}',
                    f"Your video is uploaded and will go public {local}.\n\nhttps://youtu.be/{vid}\nStudio: https://studio.youtube.com/video/{vid}/edit\n\n"
                    f"Format: {meta.get('format')} · {entry['minutes']} min\nPinned comment to add: {sb.get('pinned_comment', '')}\n\n"
                    f"Thumbnail B (for Test & Compare) is in {self.dir}", [tA, sheet])
        log.info('DONE — https://youtu.be/%s goes public %s', vid, local)
        return dict(entry, video=str(final))

    def preview(self, sb, timings):
        """Render a few stills per section (fast visual check without a full render)."""
        from .render.timeline import render_section, section_layout
        outs = []
        for i, (sec, tm) in enumerate(zip(sb['sections'], timings)):
            lead = 0.0 if i == 0 else CHAPTER_LEAD
            beats, dur = section_layout(sec, tm, lead)
            ts = [b['_t0'] + 1.6 for b in beats]
            render_section(dict(sec=sec, timing=tm, lead=lead, chapter_no=i, out=str(self.dir / f'preview_s{i:02d}'), preview_t=ts))
            outs.append(i)
        log.info('preview stills written to %s', self.dir)
        return dict(preview=str(self.dir))


def main(cfg, args, llm_factory):
    r = None
    try:
        with Lock():
            r = Run(cfg, args)
            return r.execute(llm_factory)
    except QueueFull as e:
        log.info('%s', e); return dict(skipped=str(e))
    except Exception as e:
        tb = traceback.format_exc()
        log.error('RUN FAILED: %s\n%s', e, tb)
        where = r.dir if r else RUNS
        notify.send(cfg, '❌ YouTube engine run failed', f'{e}\n\nLog folder: {where}\n\n{tb[-3000:]}')
        raise
