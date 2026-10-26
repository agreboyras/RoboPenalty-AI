"""Strict Spanish command grammar; shared by text and local ASR."""
import re
import unicodedata

LABELS={'center':'central','left_near_b060':'centro-izquierda (opción izquierda disponible)',
        'right_inter_m080':'intermedio derecho','right_open_m100':'abierto derecho','right_corner_m140':'esquina derecha'}
def normalize(text):
    return ' '.join(re.findall(r'[a-z0-9]+',''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if unicodedata.category(c)!='Mn')))

def interpret(text):
    phrase=normalize(text)
    phrase=re.sub(r'^por favor ','',phrase);phrase=re.sub(r' por favor$','',phrase)
    if phrase in ('ayuda','help'):return 'help'
    if phrase in ('estado','mostrar estado','ver estado'):return 'state'
    if phrase in ('salir','cerrar','salir del juego'):return 'stop'
    if phrase in ('microfono','activar microfono','escuchar','escuchar orden'):return 'listen'
    if re.fullmatch(r'(cambiar a |activar |usar )?modo (automatico|auto)',phrase):return 'mode:auto'
    if re.fullmatch(r'(cambiar a |activar |usar )?modo (dirigido|manual)',phrase):return 'mode:directed'
    from phase6b.commands import interpret as previous
    old=previous(phrase)
    if old:return old
    # Full match: conjunctions, multiple destinations, negations or vague corners fail closed.
    match=re.fullmatch(r'(patea|patear|tira|tirar|dispara|disparar) (?:(?:hacia la|hacia el|a la|hacia|al|a) )?(.+)',phrase)
    if match:
        destination=match[2]
        mapping={
            'centro':'center','central':'center',
            'izquierda':'left_near_b060','centro izquierda':'left_near_b060',
            'derecha':'right_inter_m080','intermedio derecho':'right_inter_m080','derecha intermedia':'right_inter_m080',
            'abierto derecho':'right_open_m100','derecha abierta':'right_open_m100','derecha mas abierta':'right_open_m100',
            'esquina derecha':'right_corner_m140'}
        if destination=='esquina izquierda':return 'unsupported:left_corner'
        return 'shot:'+mapping[destination] if destination in mapping else None
    return None
