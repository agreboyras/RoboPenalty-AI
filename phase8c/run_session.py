"""8C integration reuses the owned 8B.3 launcher and all existing game controls."""
from bootstrap import *
import argparse
import importlib.util
import json
from phase8c.catalog import load_catalog
from phase8c.runtime import components
from phase8c.integrity import sources

def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--catalog',type=Path,default=HERE/'catalog_v1.json')
    p.add_argument('--original-return',action='store_true',help='Validation only: historical return behavior')
    p.add_argument('--output',type=Path)
    a,args=p.parse_known_args()
    spec=importlib.util.spec_from_file_location('phase8c_owned_session',PROJECT/'phase8b3/run_session.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    catalog=load_catalog(a.catalog)
    launcher.HERE=HERE
    launcher.ShotCatalog=lambda ignored:catalog
    launcher.components=lambda c,posture:components(c,posture,correct_return=not a.original_return)
    if a.output:args+=['--output',str(a.output)]
    sys.argv=[str(HERE/'run_session.py'),*args];before=sources()
    try:launcher.main()
    finally:
        after=sources();changed=[key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)]
        if a.output and a.output.is_dir():
            (a.output/'protected_sources.json').write_text(json.dumps(dict(checked=len(before),changed=changed),indent=2),encoding='utf-8')
            path=a.output/'session.json'
            if path.exists():
                data=json.loads(path.read_text());data['phase8c']=dict(catalog_sha256=catalog.id,
                    actions=catalog.actions,return_extension=not a.original_return)
                path.write_text(json.dumps(data,indent=2),encoding='utf-8')
        if changed:raise RuntimeError(changed)
if __name__=='__main__':main()
