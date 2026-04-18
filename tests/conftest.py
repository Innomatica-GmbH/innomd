"""Put the repo root on sys.path so `import innomd` works in tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_innomd():
    import innomd
    return innomd
