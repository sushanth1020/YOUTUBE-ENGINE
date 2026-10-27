"""Thin wrapper over the Anthropic Messages API (streaming, server-side web search, JSON repair)."""
import json
from .config import env
from .util import extract_json, log


class LLM:
    def __init__(self, cfg):
        import anthropic
        self.client = anthropic.Anthropic(api_key=env('ANTHROPIC_API_KEY', required=True), max_retries=4)
        self.cfg = cfg['llm']
        self.usage = {'input_tokens': 0, 'output_tokens': 0, 'web_searches': 0}

    def _call(self, system, messages, searches=0, max_tokens=None):
        kw = dict(model=self.cfg['model'], max_tokens=max_tokens or self.cfg.get('max_tokens', 32000), system=system, messages=messages)
        if searches:
            kw['tools'] = [{'type': self.cfg.get('web_search_tool', 'web_search_20250305'), 'name': 'web_search', 'max_uses': int(searches)}]
        if self.cfg.get('thinking_budget'):
            kw['thinking'] = {'type': 'enabled', 'budget_tokens': int(self.cfg['thinking_budget'])}
        with self.client.messages.stream(**kw) as st:
            msg = st.get_final_message()
        u = msg.usage
        self.usage['input_tokens'] += getattr(u, 'input_tokens', 0) or 0
        self.usage['output_tokens'] += getattr(u, 'output_tokens', 0) or 0
        stu = getattr(u, 'server_tool_use', None)
        if stu: self.usage['web_searches'] += getattr(stu, 'web_search_requests', 0) or 0
        return msg

    def ask(self, system, user, searches=0, max_tokens=None, history=None):
        """Returns (text, sources, messages). Continues automatically on pause_turn (long server-tool turns)."""
        messages = list(history or []) + [{'role': 'user', 'content': user}]
        texts, sources = [], []
        for _ in range(8):
            msg = self._call(system, messages, searches, max_tokens)
            for b in msg.content:
                if b.type == 'text': texts.append(b.text)
                elif b.type == 'web_search_tool_result' and isinstance(getattr(b, 'content', None), list):
                    for r in b.content:
                        if getattr(r, 'url', None): sources.append({'title': getattr(r, 'title', ''), 'url': r.url})
            messages.append({'role': 'assistant', 'content': msg.content})
            if msg.stop_reason == 'pause_turn': continue
            if msg.stop_reason == 'max_tokens': log.warning('LLM hit max_tokens')
            break
        return ''.join(texts), sources, messages

    def ask_json(self, system, user, searches=0, check=None, retries=2, max_tokens=None, tolerate=None):
        """Ask for a JSON object; on parse/validation errors, show the model its errors and ask for a fix."""
        text, sources, messages = self.ask(system, user, searches, max_tokens)
        for attempt in range(retries + 1):
            try:
                obj = extract_json(text)
                errs = check(obj) if check else []
                if not errs: return obj, sources
                if attempt == retries and tolerate and all(tolerate(e) for e in errs):
                    log.warning('accepting JSON with minor issues: %s', errs); return obj, sources
                problem = 'The JSON has these problems:\n- ' + '\n- '.join(errs[:25])
            except Exception as e:
                problem = f'Your reply could not be parsed as one JSON object ({e}).'
            if attempt == retries: raise ValueError(problem)
            log.warning('LLM JSON repair round %d: %s', attempt + 1, problem[:300])
            text, s2, messages = self.ask(system, problem + '\nReturn the COMPLETE corrected JSON object only, no commentary.',
                                          0, max_tokens, history=messages)
            sources += s2
        raise ValueError('unreachable')
