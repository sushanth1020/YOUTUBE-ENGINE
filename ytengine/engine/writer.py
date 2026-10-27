"""Research brief -> storyboard -> fact-check -> revision, all with Claude."""
import json
from . import prompts as P
from .storyboard import problems, normalize, word_count
from .util import log


def _audience(cfg):
    return P.AUDIENCE.get(cfg['channel'].get('audience', 'mix'), P.AUDIENCE['mix'])


def plan(llm, cfg, ctx):
    system = P.PLANNER_SYSTEM.format(niche=cfg['channel']['niche'], audience_desc=_audience(cfg), persona=cfg['channel']['persona'])
    user = P.PLANNER_USER.format(**ctx)

    def check(o):
        errs = []
        for k in ('topic', 'facts', 'title_options', 'outline'):
            if not o.get(k): errs.append(f'missing "{k}"')
        if len(o.get('facts', [])) < 6: errs.append('need at least 6 sourced facts')
        return errs
    brief, sources = llm.ask_json(system, user, searches=cfg['llm'].get('research_searches', 12), check=check)
    brief['_search_sources'] = sources[:40]
    log.info('topic: %s | angle: %s', brief.get('topic'), brief.get('angle'))
    return brief


def _chapters(minutes):
    return 3 if minutes <= 5 else 4 if minutes <= 8 else 5 if minutes <= 10 else 6


def write(llm, cfg, brief, fmt, minutes, watch_next):
    words = int(minutes * cfg['content'].get('words_per_minute', 150))
    system = P.WRITER_SYSTEM.format(persona=cfg['channel']['persona'], audience_desc=_audience(cfg), words=words,
                                    chapters=_chapters(minutes), watch_next=watch_next or 'another video on the channel')
    b = {k: v for k, v in brief.items() if not k.startswith('_')}
    user = P.WRITER_USER.format(format=fmt, format_note=cfg['content']['formats'][fmt]['note'], minutes=minutes, words=words,
                                chapters=_chapters(minutes), brief=json.dumps(b, ensure_ascii=False, indent=1), example=P.WRITER_EXAMPLE)

    def check(sb):
        errs = problems(sb)
        wc = sum(len(' '.join(s.get('sentences', [])).split()) for s in sb.get('sections', []))
        if wc < words * 0.8: errs.append(f'script is {wc} words; target is ~{words}. Expand it (more story, data and takeaways).')
        if wc > words * 1.25: errs.append(f'script is {wc} words; target is ~{words}. Tighten it.')
        return errs
    sb, _ = llm.ask_json(system, user, searches=0, check=check, retries=2, tolerate=lambda e: 'words; target' in e)
    return sb, system


def verify_and_fix(llm, cfg, brief, sb, minutes, writer_system):
    words = int(minutes * cfg['content'].get('words_per_minute', 150))
    b = {k: v for k, v in brief.items() if not k.startswith('_')}
    rep, _ = llm.ask_json(P.VERIFY_SYSTEM, P.VERIFY_USER.format(words=words, actual=word_count(sb),
                          brief=json.dumps(b, ensure_ascii=False), storyboard=json.dumps(sb, ensure_ascii=False)),
                          searches=cfg['llm'].get('verify_searches', 8))
    issues = rep.get('issues') or []
    log.info('fact-check: approved=%s, %d issues', rep.get('approved'), len(issues))
    if rep.get('approved') and not issues: return sb, rep
    fixed, _ = llm.ask_json(writer_system, P.REVISE_USER.format(issues=json.dumps(issues, ensure_ascii=False, indent=1),
                            storyboard=json.dumps(sb, ensure_ascii=False)), check=problems, retries=2)
    return fixed, rep


def make_storyboard(llm, cfg, ctx, fmt, minutes, watch_next):
    brief = plan(llm, cfg, ctx)
    sb, wsys = write(llm, cfg, brief, fmt, minutes, watch_next)
    sb, report = verify_and_fix(llm, cfg, brief, sb, minutes, wsys)
    sb = normalize(sb)
    sb['_meta'] = dict(format=fmt, minutes=minutes, topic=brief.get('topic'), angle=brief.get('angle'),
                       people=[p.get('wiki_title') for p in brief.get('people', [])], factcheck=report)
    return brief, sb
