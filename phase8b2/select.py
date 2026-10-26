"""Freeze a catalog only after two identical full-duration free-flight trials."""
from bootstrap import *
import argparse
import hashlib
import json
import os
from phase8b2.experiment import identifier
from phase5.benchmark import compare_physics

SELECTION={'center':0.,'intermediate_left_b110':1.1,'intermediate_right_m080':-.8,
           'corner_left_b097':.97,'corner_right_m140':-1.4}
def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New catalog in phase8b2 required')
    entries={}
    for action,bias in SELECTION.items():
        path=a.input/f'{identifier(bias)}_01.json';second=a.input/f'{identifier(bias)}_02.json'
        r,s=[json.loads(p.read_text(encoding='utf-8')) for p in (path,second)]
        for t in (r,s):
            if not t['passed'] or not t['evaluation']['goal_detected']:raise AssertionError('Candidate is not valid')
        compare_physics(r,s)
        for key in ('trajectory','positive_foot_contacts','final_state_sha256'):
            if r['phase8b2'][key]!=s['phase8b2'][key]:raise AssertionError('Candidate is not exactly reproducible')
        entries[action]={'bias':bias,'probe':os.path.relpath(path,a.output.parent).replace('\\','/'),
                         'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                         'validation':'two exact 14s probes, physical trace, 500Hz trajectory, contacts, final full state hash'}
    a.output.write_text(json.dumps(dict(version=1,actions=entries),indent=2),encoding='utf-8')
    from phase8b2.catalog import ShotCatalog
    catalog=ShotCatalog(a.output)
    print(json.dumps(dict(catalog_sha256=catalog.id,actions=catalog.actions,exact_repeats=True)))
if __name__=='__main__':main()
