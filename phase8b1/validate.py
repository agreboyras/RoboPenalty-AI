"""Exact comparisons only where the same planner is expected."""
import argparse
import json
from bootstrap import *
from phase7b.validate import compare

def main():
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):raise ValueError('New phase8b1 report required')
    result=compare(a.reference,a.candidate)
    result['note']='Exact comparison for the same planner; not used to require old outcomes from new planners.'
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print('PASS exact full match comparison')

if __name__=='__main__':main()
