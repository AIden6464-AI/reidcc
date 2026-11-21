import sys
from pathlib import Path

# Make the project root importable (proxy.py, claude_optimizer_addon.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
