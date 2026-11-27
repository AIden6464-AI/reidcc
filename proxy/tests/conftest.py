import sys
from pathlib import Path

# Make the project root importable (claude_optimizer_addon.py and the other add-ons).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
