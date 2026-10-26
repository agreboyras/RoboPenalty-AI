"""Explicit bounded bias search; rejected trials remain on disk."""
from bootstrap import *
import argparse
import json
from phase8b2.experiment import BiasRuntime,identifier,summarize

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--biases',type=float,nargs='+',required=True)
    p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New output inside phase8b2 required')
    if a.repeats<1 or len({identifier(b) for b in a.biases})!=len(a.biases):p.error('Unique finite biases and positive repeats required')
    a.output.mkdir(parents=True)
    runtime=BiasRuntime(); summaries=[]
    for b in a.biases:
        for n in range(a.repeats):
            path=a.output/f'{identifier(b)}_{n+1:02d}.json'
            r=runtime.trial(b,path);s=summarize(r,path);summaries.append(s)
            (a.output/'summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')
            print(json.dumps(dict(bias=b,repeat=n+1,outcome=s['outcome'],y5=s['plane5']['position_w'][1] if s['plane5'] else None,
                fall=s['fall'],failures=s['failures'],wall_s=s['wall_s'])),flush=True)
            if s['fall'] is not None or any(r['engine_warnings']):
                print('STOP: physical instability; no subsequent experiments executed.',flush=True);return 2
    (a.output/'runtime.json').write_text(json.dumps(runtime.summary(),indent=2),encoding='utf-8')
    return 0
if __name__=='__main__':sys.exit(main())
