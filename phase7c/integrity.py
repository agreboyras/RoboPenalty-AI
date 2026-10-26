"""Protect previous phases, including 7B, and the external robot dependencies."""
import hashlib
from pathlib import Path
from phase7b.integrity import protected_sources as previous_sources, model_signature as base_signature, save

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent

def protected_sources():
    result={p:h for p,h in previous_sources().items() if not Path(p).is_relative_to(HERE)}
    for p in (PROJECT/'phase7b').rglob('*'):
        if p.is_file() and not {'results','__pycache__'}.intersection(p.relative_to(PROJECT/'phase7b').parts):
            result[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result

def model_signature(model):
    result=base_signature(model)
    # Only RGB texture pixels are additionally visual. Texture dimensions,
    # mappings, materials, meshes and ALL physical arrays are still fingerprinted.
    result['arrays'].pop('tex_data',None)
    return result
