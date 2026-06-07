from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
TASKS_DIR = DATA_DIR / "tasks"
STATIC_DIR = Path(__file__).resolve().parent / "static"
