import os
from pathlib import Path

ROOT_DIR = Path(os.environ.get("ROOT_DIR", Path(__file__).resolve().parents[4]))