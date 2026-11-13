"""Compatibility launcher; application modules live in app/."""
import sys
from pathlib import Path
import runpy
sys.path.insert(0,str(Path(__file__).resolve().parent/"app"))
if __name__=="__main__":
    runpy.run_path(str(Path(__file__).resolve().parent/"app/desktop.py"),run_name="__main__")
