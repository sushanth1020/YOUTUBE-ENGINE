import os
from pathlib import Path
import yaml
from .util import ROOT

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
except ImportError:
    pass


class Cfg(dict):
    """dict with attribute access for nested config."""
    def __getattr__(self, k):
        v = self.get(k)
        return Cfg(v) if isinstance(v, dict) else v


def load(path=None):
    p = Path(path) if path else ROOT / 'config.yaml'
    return Cfg(yaml.safe_load(p.read_text(encoding='utf-8')))


def env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v: raise RuntimeError(f'Missing {name} in .env')
    return v
