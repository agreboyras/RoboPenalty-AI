import hashlib
from pathlib import Path
from phase7d.integrity import protected_sources as previous
HERE=Path(__file__).resolve().parent
def protected_sources():
    result={p:h for p,h in previous().items() if not Path(p).is_relative_to(HERE)}
    for p in (HERE.parent/'phase7d').rglob('*'):
        if p.is_file() and not {'results','__pycache__'}.intersection(p.relative_to(HERE.parent/'phase7d').parts):
            result[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result
