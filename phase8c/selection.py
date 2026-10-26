"""Freeze only explicitly evaluated actions, with honest target-role labels."""
from bootstrap import *
import argparse
import hashlib
import json
import os
from phase8c.criteria import assess
SELECTION={
    'center':(0.,'central','historical_grid'),
    'left_near_b060':(.6,'near_center_left','conservative_grid'),
    'right_inter_m080':(-.8,'intermediate_right','historical_grid'),
    'right_open_m100':(-1.,'open_right','final_candidate_grid'),
    'right_corner_m140':(-1.4,'lower_corner_right','historical_grid'),
}

def resolve_source(value):
    p=Path(value)
    for candidate in (p,PROJECT.parent/p,PROJECT/p):
        if candidate.is_file():return candidate.resolve()
    raise FileNotFoundError(value)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--strict-core-only',action='store_true');a=p.parse_args()
    if a.output.exists() or not a.output.resolve().is_relative_to(HERE):p.error('New catalog required')
    entries={}
    for action,(bias,role,folder) in SELECTION.items():
        if a.strict_core_only and role=='near_center_left':continue
        rows=[r for r in json.loads((HERE/'results'/folder/'summary.json').read_text()) if r['bias']==bias]
        unique={r['delta_y_m']:r for r in rows};screen=assess(list(unique.values()))
        accepted=screen['passes_engineering_screen']
        if role=='near_center_left':accepted=screen['passes_physical_consistency_screen'] and screen['positive_y_all']
        if not accepted:raise ValueError(f'{action} fails declared acceptance: {screen}')
        nominal=next(r for r in rows if r['delta_y_m']==0. and r['repeat']==1)
        source=resolve_source(nominal['source'])
        grid=[]
        for delta,r in sorted(unique.items()):
            path=resolve_source(r['source']);grid.append(dict(delta_y_m=delta,source=os.path.relpath(path,a.output.resolve().parent).replace('\\','/'),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        entries[action]=dict(bias=bias,role=role,probe=os.path.relpath(source,a.output.resolve().parent).replace('\\','/'),
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),grid=grid,assessment=screen)
    a.output.write_text(json.dumps(dict(version=1,actions=entries,
        scope='Enumerated Y offsets ±5/2/1/0mm only. Near-center-left does not claim intermediate/corner sector consistency. No left-corner action in consolidated catalog.'),indent=2),encoding='utf-8')
    from phase8c.catalog import Catalog
    catalog=Catalog(a.output);print('Catalog frozen:',catalog.actions,catalog.id)
if __name__=='__main__':main()
