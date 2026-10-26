"""Explicit resource-only adapter for the historical 3A/3B/4A experiment runners."""
from pathlib import Path
import argparse
import importlib.util
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('phase2','phase3a','phase3b'):sys.path.insert(0,str(ROOT/name))
from portability.resources import install

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=['phase3a','phase3b','phase4a'],default='phase4a')
    p.add_argument('--mode',default='probe');p.add_argument('--scenario',default='long_center')
    p.add_argument('--case',default='return');p.add_argument('--duration',type=float,default=14.)
    p.add_argument('--viewer',action='store_true');p.add_argument('--unpaced',action='store_true');p.add_argument('--output',required=True)
    args=p.parse_args();path=ROOT/args.phase/'experiment.py'
    sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('portable_historical_experiment',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if not hasattr(module,'HOME'):module.HOME=path.parent
    install(module)
    raise SystemExit(module.run(args))
if __name__=='__main__':main()
