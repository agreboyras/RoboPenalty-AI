"""One-time migration of dependency hashes; never publishes the private baseline."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def main():
    original=json.loads((ROOT/'phase2/results/benchmark/single_01.json').read_text(encoding='utf-8'))
    roots={name:(ROOT.parent/name).resolve() for name in ('RoboNaldo_Deploy','unitree_mujoco')}
    rows=[]
    for name,expected in original['external_inputs']['files_sha256'].items():
        path=Path(name).resolve()
        matches=[root for root,base in roots.items() if path.is_relative_to(base)]
        if len(matches)!=1:raise ValueError('Dependency outside documented external roots')
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=expected:raise ValueError('External dependency changed; refusing migration')
        key=matches[0];rows.append(dict(root=key,path=path.relative_to(roots[key]).as_posix(),sha256=expected))
    result=dict(version=1,role='External file integrity only; not a simulation outcome or physics baseline',files=sorted(rows,key=lambda r:(r['root'],r['path'])))
    target=ROOT/'portability/external_manifest.json'
    if target.exists():raise ValueError('Public manifest already exists')
    target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Migrated and verified',len(rows),'relative dependency hashes; original untouched')
if __name__=='__main__':main()
