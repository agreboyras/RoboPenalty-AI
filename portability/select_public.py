"""Explicit public allowlist. Never stages files or rewrites historical records."""
import json
from pathlib import Path
import re
import ast
import io
import tokenize
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'publication'
PRIVATE=re.compile(r'(?i)(?:[A-Z]:[\\/]+Users[\\/]+|/(?:home|Users)/[^/\s]+/)')
EMAIL=re.compile(r'(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}')
SECRET=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|https?://[^\s/@:]+:[^\s/@]+@)')

def concerns(path):
    text=path.read_text(encoding='utf-8',errors='strict')
    if path.suffix=='.py':
        tree=ast.parse(text)
        strings=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        comments=[t.string for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type==tokenize.COMMENT]
        text='\n'.join(strings+comments)  # Matrix @ expressions are not email addresses.
    # JSON encodes Windows separators twice; normalize only for inspection, never saved.
    normalized=text.replace('\\\\','\\')
    found=[]
    if PRIVATE.search(normalized) or ('@' in normalized and EMAIL.search(normalized)):found.append('personal_path_or_email')
    if SECRET.search(normalized):found.append('credential_candidate')
    if path.suffix=='.md' and re.search(r'Carrello|Realtek|capture_\d+|RMS\s*[:=]|transcripci[oó]n\s*:',text,re.I):
        found.append('historical_voice_or_device_document')
    if path.suffix=='.json' and 'results' in path.parts:
        if re.search(r'"(?:text|transcript(?:ion)?|recognized_text|device|devices|device_name|device_index|native_device)"\s*:',text,re.I):
            found.append('voice_or_device_record')
    return found

def main():
    selected=set();excluded=[]
    for phase in ROOT.glob('phase*'):
        for path in phase.rglob('*'):
            if not path.is_file() or {'results','models','__pycache__'}.intersection(path.relative_to(phase).parts):continue
            if path.suffix not in ('.py','.json','.xml','.yaml','.yml','.md','.svg'):continue
            if path.name=='RESULTADOS.md' or path.name.endswith('_RESULTADOS.md'):continue
            reasons=concerns(path)
            if reasons:excluded.append(dict(path=path.relative_to(ROOT).as_posix(),reasons=reasons));continue
            selected.add(path.relative_to(ROOT).as_posix())
    required=[]
    for catalog in (ROOT/'phase8b2/catalog_v1.json',ROOT/'phase8c/catalog_v1.json'):
        raw=json.loads(catalog.read_text())
        for entry in raw['actions'].values():
            required.extend(catalog.parent/v for v in [entry['probe']]+[r['source'] for r in entry.get('grid',[])])
    for folder,name in [('exploration','center'),('exploration','preset_left'),('exploration','preset_right'),
        ('exploration','long_center'),('calibration_probes','long_preset_left'),('calibration_probes','long_preset_right')]:
        required.append(ROOT/f'phase4a/results/{folder}/{name}_probe_01.json')
    # Historical visual tests initialize from this numeric state, not from voice/session logs.
    required.append(ROOT/'phase7b/results/final_headless/match_001/penalty_01/physical.json')
    required.append(ROOT/'phase8b3/results/audit.json')  # Numeric joint fixture for unchanged PD tests.
    for path in set(required):
        reasons=concerns(path)
        if reasons:raise RuntimeError(f'Private mandatory calibration: {path.relative_to(ROOT)} {reasons}')
        selected.add(path.relative_to(ROOT).as_posix())
    for path in (ROOT/'portability').glob('*'):
        if path.is_file() and path.suffix in ('.py','.json','.md'):selected.add(path.relative_to(ROOT).as_posix())
    selected.update(['run_robopenalty.py','README.md','requirements.txt','requirements-voice.txt','THIRD_PARTY.md',
        '.gitignore','.gitattributes','docs/DEPENDENCIAS_EXTERNAS.md','portability/README.md'])
    selected.add('phase6b/models/whisper-tiny/MODEL_NOT_INCLUDED.md')
    selected.add('phase6b/results/.gitkeep')
    report=dict(files=sorted(selected),excluded_historical_sources_or_docs=excluded,
        note='All raw logs, results other than exact mandatory safe calibrations, archives, audio and model files excluded. Original files untouched.')
    (OUT/'public_selection.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Public candidates:',len(selected),'excluded historical documents/tools:',len(excluded))
    print('Mandatory calibration records:',len(set(required)))
if __name__=='__main__':main()
