from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;PROJECT=HERE.parent
for p in (PROJECT,PROJECT/'phase2',PROJECT/'phase3a',PROJECT/'phase3b',PROJECT/'phase5',PROJECT/'phase6b'):
    sys.path.insert(0,str(p))
