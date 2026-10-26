"""Publish results only from completed, validated artifacts."""
from bootstrap import *
import json
import math
from phase8b2.integrity import protected_sources

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def main():
    root=HERE/'results'
    if (HERE/'RESULTADOS.md').exists():raise ValueError('Results already published; preserve previous evidence')
    catalog=read(HERE/'catalog_v1.json')
    selected=read(root/'selected_repeats/summary.json')
    summaries={s['bias']:s for s in selected}
    fixed=read(root/'fixed/summary.json');agents=read(root/'agents/summary.json')
    rows=fixed+agents
    for report in ('fixed_exact.json','agents_exact.json','headless_viewer_exact.json','reference_A_exact.json','reference_B_exact.json'):
        assert read(root/report)['passed'],report
    tests=read(root/'regressions/tests.json');assert all(r['returncode']==0 for r in tests)
    before=read(root/'protected_before.json');after=protected_sources()
    assert before==after,'Historical sources changed'
    sessions={name:read(root/name/'session.json') for name in ('match_headless','match_viewer','learning_10','reference_A','reference_B')}
    for name,s in sessions.items():assert s['failure'] is None and not s['previous_sources_changed'],name
    matches={name:read(root/name/'match_001/match.json') for name in sessions}
    sweep=read(root/'analysis/candidates.json')
    unit_count=sum(r['count'] or 0 for r in tests)
    lines=['# Fase 8B.2 — Resultados medidos','',
        '## Conclusión','',
        'Se encontraron y repitieron tiros físicos a ambas esquinas inferiores sin modificar la habilidad motriz, la física ni el arquero B. Se integra un catálogo experimental independiente de cinco acciones. No se reemplazan presets históricos ni se declara superioridad del aprendizaje o del arquero por el nuevo marcador.','',
        f'Barrido: {len(sweep)} episodios, {len(set(r["bias"] for r in sweep))} valores distintos. Todos duraron 14 s simulados. Se conservan también tiros cortos, invertidos, errados y sin contacto. La tabla completa por bias está en [TABLA](results/analysis/TABLA.md); cada repetición y sus métricas en [CSV](results/analysis/candidates.csv) y JSON.','',
        '## Candidatos seleccionados (arquero apartado)','',
        '| Acción nueva | Bias | Y X=4 m | Y X=5 m | Z X=5 m | Tiempo X=5 s | Ángulo salida ° | Margen esfera/poste m | Fuerza pie N |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for action,entry in catalog['actions'].items():
        s=summaries[entry['bias']];p4=s['plane4'];p5=s['plane5']
        lines.append(f"| {action} | {entry['bias']:+.2f} | {p4['position_w'][1]:+.6f} | {p5['position_w'][1]:+.6f} | {p5['position_w'][2]:.6f} | {p5['time_sim_s']:.6f} | {s['release_angle_deg']:+.3f} | {s['sphere_post_margin_m']:.6f} | {s['foot_peak_n']:.2f} |")
    lines+=['',
        'Los cruces son interpolaciones de pasos físicos de 2 ms. La salida es la primera muestra sin fuerza pie–pelota posterior al último contacto positivo. Los JSON de las calibraciones seleccionadas incluyen posición, velocidad, puntos de contacto, fuerzas y trayectoria a 500 Hz; los barridos iniciales conservan trayectoria y fuerza, pero no todos contienen puntos de contacto detallados. Se midió el radio original 0,115 m y se usa para el margen nominal, sin modificar el detector.','',
        'Cada candidata tiene dos repeticiones exactamente iguales en estados iniciales, traza física, trayectoria a 500 Hz, contactos positivos y hash del estado final completo. Fueron descartados +1,15 y +2,00 por ausencia de contacto; +0,90, +1,20, +1,25 y +1,30 por falta de llegada; −2,00 por tiro errado. +0,94, −1,50 y −1,75 pueden ser goles según la regla original del centro pero no tienen margen nominal suficiente para la esfera. +0,96 es demasiado próximo al poste para preferirlo frente a +0,97.','',
        'El bias no es monotónico: +1,75 produce un tiro hacia Y negativo; +0,94, +0,97 y +0,98 tienen llegadas muy diferentes. Por eso se congela cada calibración. Repetibilidad determinista no prueba robustez ante perturbaciones.','',
        'También se midieron tiros abiertos intermedios: +1,05 llegó a Y=+0,9425 m y −1,00 a Y=−0,8806 m. No se añadieron al catálogo de cinco para evitar aumentar todavía más la exploración inicial; sus resultados se conservan como candidatos, no como presets seleccionados con dos repeticiones.','',
        '## Comparación pareada de arqueros','',
        'Cada combinación se repitió dos veces, con condiciones iniciales iguales salvo la estrategia. La pelota coincide con el ensayo libre hasta el primer contacto con arquero según el control preexistente de 1e−8; en estos ensayos el error observado fue cero. No se declara atajada por mera ausencia de gol.','',
        '| Acción | Arquero | Resultado | Consigna máx. antes del cruce m | q real al cruce m | Separación mínima superficial antes de gol m |',
        '|---|---|---|---:|---:|---:|']
    for action in catalog['actions']:
        for v in ('fixed','A','B'):
            r=next(s for s in rows if s['action']==action and s['variant']==v and s['repeat']==1)
            lines.append(f"| {action} | {v} | {r['outcome']} | {r['maximum_command_before_critical_m']:.6f} | {r['actual_q_at_critical_m']:.6f} | {r['minimum_surface_before_goal_sampled_m']:.6f} |")
    lines+=['',
        'q positivo corresponde a Y mundial negativo. La distancia superficial es el mínimo **muestreado a 50 Hz**, no un mínimo continuo. Los valores negativos representan penetración/contacto en MuJoCo. Las métricas de reacción, predicción, velocidad, aceleración, fuerza, contacto y seguimiento están en `fixed/summary.json`, `agents/summary.json` y `planning.json` por penal. Si el central se bloquea antes de X=4, el instante crítico es el primer contacto y no un cruce inventado.','',
        'B mejora la aproximación lateral respecto de A, pero los cuatro tiros laterales siguen siendo goles frente a los tres oponentes. No hay evidencia de una ventaja en atajadas en este catálogo. Las esquinas demandan una cobertura que el mecanismo actual no alcanza a tiempo; no se aumentaron velocidad, fuerza, recorrido ni referencias corporales.','',
        '## Estabilidad y límites','',
        f'En las 30 ejecuciones pareadas: ninguna caída ni advertencia MuJoCo. Pico máximo de velocidad lateral {max(r["rail"]["peak_speed_mps"] for r in rows):.6f} m/s; aceleración medida {max(r["rail"]["peak_acceleration_mps2"] for r in rows):.6f} m/s²; fuerza {max(r["rail"]["peak_force_n"] for r in rows):.6f} N. Se aplicaron los mismos límites/umbrales históricos.','',
        'Los dos pares por combinación fueron comparados exactamente, incluyendo trayectoria, contactos, agente, consignas y estado final. El modelo compilado se verifica por firma física; el apartamiento del arquero pertenece únicamente a la inicialización del ensayo libre y se restaura después.','',
        '## Tandas y aprendizaje','',
        '| Ejecución | Goles | Atajadas | Errados | Episodios | Tiempo real total s | Inicialización antes del visor s |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for name,s in sessions.items():
        m=matches[name];b=m['scoreboard']
        lines.append(f"| {name} | {b['goals']} | {b['saves']} | {b['misses']} | {len(b['history'])} | {s['script_wall_s']:.3f} | {s['initialization_before_viewer_s']:.3f} |")
    lines+=['',
        'La tanda nueva tiene 35.000 pasos y 70 s simulados. Modelo y política se cargan una vez por proceso; cada reinicio coincide con MjData fresco y conserva la identidad de la sesión ONNX. La pausa por texto no modifica el estado completo. La variante visual coincide exactamente con headless en estados, trayectoria, contactos, decisiones, aprendizaje y resultados; no se compara solo el marcador.','',
        'Orden de la tanda de cinco: '+', '.join(f"{r['action']} ({r['outcome']})" for r in matches['match_headless']['scoreboard']['history'])+'.','',
        'La tanda de diez conserva los conteos y permite elegir después de explorar las cinco acciones. Decisiones 6–10:']
    for n in range(6,11):
        d=read(root/'learning_10/match_001'/f'penalty_{n:02d}/decision_before_shot.json')['decision']
        lines.append(f"- {n}: `{d['action']}`, `{d['reason']}`, utilidad {d['candidates'][d['action']]['utility']:.6f}, {d['completed_episodes_before']} episodios previos.")
    lines+=['',
        'La fórmula/prior originales no cambian. Se observa actualización estadística y selección posterior, no una comparación suficiente para afirmar mejor aprendizaje. Las estadísticas se aislaron por SHA-256 del catálogo; se rechaza cargar el historial de acciones con trayectorias distintas.','',
        '## Regresiones y evidencia visual','',
        f'{unit_count} tests pasaron, incluyendo configuración/catálogo, aprendizaje causal, planificadores, predictor, evaluación, agentes históricos, estadio y parser estricto. {len(before)} fuentes/documentos anteriores permanecen idénticos al manifiesto inicial. El runner verifica además las 209 dependencias externas históricas en cada episodio.','',
        'Las referencias A y B de tres acciones se volvieron a ejecutar: SAVE, GOAL, SAVE, GOAL, GOAL; 3–2, 35.000 pasos. Comparación exacta con sus referencias archivadas, sin modificar archivos anteriores.','',
        'Capturas reales MuJoCo en `results/match_viewer/`: inicial, intercepción, ambas esquinas próximas a X=5 y final, con vistas detrás, ejecución, general y arco. Se reutiliza el estadio 7D intacto. `headless_viewer_exact.json` contiene la validación.','',
        'Los tiempos totales incluyen instrumentación, carga/importaciones, consola y comprobaciones; el visual incluye pacing, pausas y capturas RGB. No son un benchmark aislado de la política o del render, ni FPS del visor. Los tiempos por penal/loop y pausas se conservan separados en JSON.','',
        f'En la corrida visual se midieron {sessions["match_viewer"]["presentation"]["capture_wall_s"]:.3f} s acumulados de captura y {sessions["match_viewer"]["presentation"]["presentation_pause_wall_s"]:.3f} s de pausas de presentación; la espera de pacing fue {sessions["match_viewer"]["presentation"]["pacing_sleep_wall_s"]:.3f} s. Son categorías instrumentadas que pueden incluir trabajo compartido; no se suman como un desglose exclusivo. Esta ejecución visual instrumentada fue más lenta que tiempo real. No se midió FPS nativo ni tiempo GPU.','',
        '## Limitaciones y siguiente decisión','',
        'Se completó esta variante experimental con evidencia reproducible en el entorno actual. No se calibró sensibilidad a errores iniciales ni variaciones de hardware. No se modificó ni evaluó el micrófono. La advertencia Hydra de compatibilidad existente se conserva; no hubo excepciones ni warnings del motor físico en las pruebas aprobadas.','',
        'Conservar B y el catálogo nuevo como variante experimental. Antes de ampliar capacidades defensivas, evaluar alcanzabilidad/cobertura física y perturbaciones pequeñas en pruebas separadas. No aumentar parámetros del arquero ni cambiar política en esta fase. La integración en otra fase requiere autorización.']
    (HERE/'RESULTADOS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (root/'final_audit.json').write_text(json.dumps(dict(passed=True,previous_files_checked=len(before),changed=[],tests_passed=unit_count,
        isolated_trials=len(sweep),paired_trials=len(rows),catalog_actions=list(catalog['actions']),
        exact_matches=['headless_viewer','historical_A','historical_B']),indent=2),encoding='utf-8')
    print('Published measured results and final audit')
if __name__=='__main__':main()
