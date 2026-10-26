"""Human listening annotations only; never infer an intention from unlabelled audio."""
import argparse
import json
from pathlib import Path
import uuid
from diagnose_audio import HERE


def annotate(review_path,numbers=None):
    review_path=Path(review_path).resolve()
    if not review_path.is_relative_to(HERE/'results'):
        raise ValueError('Review must be inside phase6b/results')
    review=json.loads(review_path.read_text(encoding='utf-8'))
    takes=[t for t in review['captures'] if not numbers or t['number'] in numbers]
    if not takes or (numbers and set(numbers)-{t['number'] for t in takes}):
        raise ValueError('Requested capture not available in this review')
    import winsound
    annotations=[];output=review_path.parent/f'etiquetas_{uuid.uuid4().hex}.json'
    print('No se mostrara la transcripcion de Whisper antes de etiquetar. No adivine texto ininteligible.')
    for take in takes:
        wav=Path(take['playback_wav']).resolve()
        if not wav.is_relative_to(review_path.parent):raise ValueError('Playback copy must be inside review directory')
        print(f'\n{take["capture_id"]} | {take["metrics"]["duration_s"]} segundos',flush=True)
        winsound.PlaySound(str(wav),winsound.SND_FILENAME)
        heard=input('Texto exacto que distingue (Enter = no se puede identificar): ').strip()
        quality=''
        while quality not in ('c','d','i','s','u'):
            quality=input('Calidad: c=claro, d=distorsionado/cortado, i=ininteligible, s=sin voz, u=incierto: ').strip().lower()
        annotations.append(dict(capture_id=take['capture_id'],source_sha256=take['source_native_sha256'],
            human_transcript=heard or None,human_quality=quality,intent=None,
            provenance='Usuario escucho el WAV nativo exportado sin ganancia ni filtros; etiqueta manual.',
            note='Intencion no inferida automaticamente. Texto desconocido o ininteligible no equivale a ausencia de una orden.'))
        output.write_text(json.dumps(dict(source_review=str(review_path),session=review['session'],annotations=annotations),
                                     indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'\nEtiquetas guardadas en {output}',flush=True)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--review',type=Path,required=True)
    p.add_argument('--captures',nargs='+',type=int);a=p.parse_args();annotate(a.review,a.captures)


if __name__=='__main__':main()
