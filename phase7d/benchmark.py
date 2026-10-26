"""Serial live-viewer benchmark; no RGB captures or concurrent test runners."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from phase7b.validate import compare

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve()
    if out.exists() or not out.is_relative_to(HERE):raise ValueError('New phase7d output required')
    out.mkdir(parents=True);report={}
    variants=[('7c',['--reference-7c']),('7d',[]),('7d_none',['--no-decoration'])]
    for name,extra in variants:
        folder=out/name
        command=[sys.executable,'-B',str(HERE/'run_session.py'),'--viewer','--once','--unpaced',
                 '--before-shot','0','--after-result','0','--before-reset','0','--end-pause','0',
                 '--script',str(HERE/'fixtures/start.json'),'--output',str(folder),*extra]
        start=time.perf_counter()
        with (out/f'{name}.log').open('w',encoding='utf-8') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
        wall=time.perf_counter()-start
        physical=compare(HERE/'results/integrated_headless',folder)
        session=json.loads((folder/'session.json').read_text(encoding='utf-8'))
        match=json.loads((folder/'match_001/match.json').read_text(encoding='utf-8'))
        report[name]={'process_wall_s':wall,'session':session,'physical_comparison':physical,
                      'simulated_s':match['total_simulated_s'],
                      'shot_records':match['scoreboard']['history']}
        (out/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(f'{name}: {wall:.3f}s; exact physics PASS',flush=True)
    report['method']={'viewer':True,'realtime_pacing':False,'fps_request':30,'penalties':5,'seed':2026,
                       'presentation_pauses_s':0,'rgb_captures':False,'serial_trials':1,
                       'note':'Default cameras differ with visual design; sync CPU time is not GPU render time or native FPS.'}
    (out/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':main()
