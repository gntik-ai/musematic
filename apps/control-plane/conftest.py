import sys
from pathlib import Path

# Insert src at position 0 so our 'platform' package takes precedence over stdlib platform.py.
# We must also evict the stdlib 'platform' module from sys.modules because pytest imports it
# during startup (before conftest runs). Purging it forces a re-import from our src/ path.
_src = str(Path(__file__).parent / "src")
if _src in sys.path:
    sys.path.remove(_src)
sys.path.insert(0, _src)

# Remove stdlib platform from the cache so our package is re-imported from src/.
# Keys to purge: 'platform' itself plus any sub-keys that were cached under it.
_to_purge = [k for k in list(sys.modules) if k == "platform" or k.startswith("platform.")]
for _key in _to_purge:
    del sys.modules[_key]
