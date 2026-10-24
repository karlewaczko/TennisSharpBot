"""Import first in every script: makes `import tennissharp` work whether or
not `pip install -e .` was run."""
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
