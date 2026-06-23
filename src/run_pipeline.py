import runpy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
runpy.run_path(str(PROJECT_ROOT / "run_pipeline.py"), run_name="__main__")
