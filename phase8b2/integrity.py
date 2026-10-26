"""Source hashes independent of experimental outputs, including unchanged B."""
import hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent

def protected_sources():
    result={}
    for phase in PROJECT.iterdir():
        if not phase.is_dir() or not phase.name.startswith('phase') or phase==HERE:continue
        for p in phase.rglob('*'):
            if not p.is_file() or {'results','__pycache__','models'}.intersection(p.relative_to(phase).parts):continue
            result[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result
