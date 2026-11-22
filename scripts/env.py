"""Load the ignored local environment without overriding deployment variables."""
import os
from pathlib import Path


def load_local_env():
    path = Path(__file__).resolve().parents[1] / '.env.local'
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))
