import hashlib
from pathlib import Path
from phase8b2.integrity import protected_sources as previous
HERE=Path(__file__).resolve().parent
def sources():
    result={p:h for p,h in previous().items() if not Path(p).is_relative_to(HERE)}
    for p in (HERE.parent/'phase8b2').glob('*'):
        if p.is_file():result[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result
