"""Explicit offline decoding experiments. No model downloads or fuzzy grammar."""
PROFILES = ('current', 'beam5', 'prompt', 'beam5_prompt')
VOCABULARY_PROMPT = (
    'Comandos de un simulador de penales: iniciar partido, mostrar marcador, '
    'pausar partido, reanudar partido, detener partido.'
)


def decoding_options(profile='current'):
    if profile not in PROFILES:
        raise ValueError(f'Unknown ASR profile: {profile}')
    result = dict(language='es', task='transcribe', beam_size=1,
                  vad_filter=True, condition_on_previous_text=False)
    if profile in ('beam5', 'beam5_prompt'):
        result['beam_size'] = 5
    if profile in ('prompt', 'beam5_prompt'):
        result['initial_prompt'] = VOCABULARY_PROMPT
    return result


def decoding_details(segments, info, intent):
    """Measurements only: no uncalibrated confidence threshold accepts commands."""
    retained=getattr(info,'duration_after_vad',None)
    text=' '.join(s.text.strip() for s in segments).strip()
    stage=('vad_no_speech' if retained==0 else 'decoder_empty' if not text
           else 'parser_unknown' if intent is None else 'recognized_intent')
    return dict(recognition_stage=stage,segments=[{key:getattr(s,key,None) for key in
        ('start','end','text','avg_logprob','no_speech_prob','compression_ratio','temperature')}
        for s in segments])
