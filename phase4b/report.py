"""Render a measured-data report from the completed replay audit."""
import argparse
from collections import Counter
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(); p.add_argument('--audit',required=True); p.add_argument('--output',required=True)
    a=p.parse_args(); audit=json.loads(Path(a.audit).read_text(encoding='utf-8'))
    output=Path(a.output).resolve()
    if not output.is_relative_to(HERE.parent) or output.exists(): raise ValueError('New report inside RoboPenalty required')
    table=[]
    for name,s in audit['summary'].items():
        o=s['outcomes']; acts=s['actions']
        table.append(f"| {name} | {s['episodes']} | {o.get('goal',0)} | {o.get('save',0)} | {o.get('miss',0)} | {acts.get('center',0)}/{acts.get('left',0)}/{acts.get('right',0)} | {s['wall_mean_s']:.3f} |")
    learned=[]
    for name,state in audit['statistics_final'].items():
        if '_utility_' not in name: continue
        history=state['history']; context=history[-1]['context']
        sequence=', '.join(f"{x['action']}:{x['outcome']}" for x in history)
        learned.append(f'### {name}\n\nSecuencia física: `{sequence}`.\n')
        learned.append('| Acción | Goles | Atajadas | Errados | Fracción empírica gol | p_gol suavizada |\n|---|---:|---:|---:|---:|---:|')
        for action,c in state['contexts'][context].items():
            n=sum(c.values())
            empirical=f"{c['goal']/n:.3f}" if n else 'sin observaciones'
            learned.append(f"| {action} | {c['goal']} | {c['save']} | {c['miss']} | {empirical} | {(c['goal']+1)/(n+3):.3f} |")
        s=audit['summary'][name]
        learned.append(f"\nPrimeros tres episodios: {s['first_three']}. Después: {s['after_first_three']}.\n")
    goal_force=[r['foot_force_peak_n'] for r in audit['physical_metrics']]
    text=f'''# Fase 4B — resultados físicos locales

## Protocolo

{audit['episodes_replayed']} episodios físicos, 14 s simulados cada uno, secuenciales y headless.
Las tres estrategias principales tienen 12 episodios por oponente: fijo y agente de
Fase 3B sin cambios. Hay además tres tiros right fijo por oponente como referencia
fuerte. No se seleccionaron episodios por resultado. Semilla de selección 2026;
random usa la misma secuencia reproducible contra ambos oponentes.

Se usó únicamente la distancia ampliada ya calibrada: delantero x=-2 m, pelota
x=-1 m, arquero x=4,2 m y arco x=5 m. Arquero inicialmente centrado. Todos los estados
físicos iniciales tienen el mismo SHA-256, incluso entre acciones. Cambia únicamente
el bias runtime del preset y la estrategia del arquero después de comenzar.

Cada estrategia/oponente arranca con historial vacío; no recibe resultados de los
otros grupos. Los probes de Fase 4A aportan solo geometría histórica al selector.
La evaluación es en línea, con aprendizaje durante la serie; no hay un conjunto
separado de generalización ni múltiples semillas de aprendizaje.

## Resultados

| Grupo (oponente/estrategia) | Episodios | Goles | Atajadas | Errados | Acciones center/left/right | Real promedio [s] |
|---|---:|---:|---:|---:|---|---:|
'''+ '\n'.join(table)+f'''

El nombre fixed_fixed_center significa oponente fijo y delantero center fijo.
agent_fixed_right significa oponente autónomo y delantero right fijo.

No se cuenta cualquier ausencia de gol como atajada. Cada save tiene contacto con
fuerza positiva pelota-arquero y un probe equivalente que entraba al arco. Todos
los tiros tuvieron contacto pie-pelota; pico de fuerza observado entre
{min(goal_force):.3f} y {max(goal_force):.3f} N. No hubo errores físicos, caídas ni
advertencias MuJoCo. Los errados no aparecieron en esta configuración: la penalización
de errado se prueba sintéticamente y no queda validada con un tiro errado físico.

## Aprendizaje y utilidades

Estimación por acción/contexto, Dirichlet neutral (1,1,1):

```
p_gol = (g+1)/(n+3)
p_errado = (m+1)/(n+3)
U = p_gol - 0.5*p_errado - 0.1*coverage
    + 0.15*sqrt(log(1+N)/(1+n))
```

Pseudocuentas, pesos y forma de coverage son supuestos de diseño. p_gol es una
estimación suavizada, no una probabilidad medida. La fracción empírica usa solo
episodios ya terminados. coverage combina y inicial del arquero con la coordenada
de intercepción HISTÓRICA del preset y una envolvente geométrica conservadora;
no representa la futura posición real del arquero. Se exploran las tres acciones
no ensayadas y luego se maximiza la utilidad, con desempates reproducibles.

Las utilidades completas antes de cada acción están en ledger.json y
decision_before_shot.json. Observe solo incrementa la acción elegida después de
14 s simulados. No se entrenan ni modifican políticas de movimiento.

'''+ '\n'.join(learned)+f'''
## Causalidad, física y regresiones

La auditoría pudo reproducir exactamente las {audit['episodes_replayed']} decisiones
usando únicamente observaciones iniciales, calibración histórica y estadísticas
anteriores. Verificó cada transición pending/feedback, identificador, ausencia de
doble actualización y estado persistente siguiente. Selección a t=0; feedback a
t=14 s. Las trayectorias previas al primer contacto del arquero coinciden con los
probes históricos a la tasa registrada de 50 Hz. El agente no recibe esos probes
como trayectoria del episodio actual ni tiene acceso a la simulación futura.

El arquero conserva sus 29 articulaciones posturales y slider dinámico; delantero
FreeKick externo, 59 actuadores en total. No se escribe qpos/qvel para fabricar un
tiro. Se conserva la clasificación de Fase 4A y sus simplificaciones: gol por cruce
del centro, postes visuales y guía lateral sin locomoción bípeda libre.

Regresiones ejecutadas por regressions.py: 23 tests del delantero, 25 del arquero,
6 de evaluación anterior, bloqueo físico de Fase 2, retorno de Fase 3A y comparación
long_preset_left de Fase 4A mediante sus scripts originales. Consultar logs de
regressions_v1 para los resultados, sin deducir su estado de este texto generado.

## Tiempo real

Suma de procesos de los {audit['episodes_replayed']} episodios: {audit['wall_process_total_s']:.3f} s.
Promedio {audit['wall_process_mean_s']:.3f} s; mínimo {audit['wall_process_min_s']:.3f} s;
máximo {audit['wall_process_max_s']:.3f} s. Se incluyen arranque, carga, lectura de
historial/calibración, verificación de archivos, simulación y salida. Los timers
internos de escena, política y bucle quedan en physical.json. No se atribuyen las
diferencias de duración a una mejora de rendimiento; los procesos no se ejecutaron
en paralelo y la carga del equipo no estuvo controlada.

## Alcance de la conclusión

La evidencia permite comparar estas condiciones y mostrar actualización estadística
real. No permite concluir superioridad general del aprendizaje sobre cualquier tiro
fijo: right fijo es una referencia fuerte y no necesita aprender si ya se conoce su
ventaja en este escenario. Superar center fijo o esta secuencia aleatoria no equivale
a generalizar contra otras posiciones, distancias, semillas o arqueros adaptativos.

Los contextos distinguen distancia, tipo de oponente conocido por configuración y
posición lateral inicial; solo se ensayó físicamente un bin lateral. Los tests
sintéticos verifican aislamiento entre contextos y respuesta de la heurística a
otras posiciones, pero no prueban eficacia física allí.

Recomendación: conservar esta capa de selección y preparar una evaluación separada
con semillas y condiciones no usadas para aprender; comparar también con la mejor
acción fija por contexto. Ampliar la calibración física antes de habilitar otras
posiciones del arquero. No es necesario entrenar otra política de movimiento para
este selector inicial. No se implementaron voz, web ni fases posteriores.

## Archivos y procedencia

Código y documentación propios en phase4b. Se importan fases previas intactas y se
leen pesos/assets externos en ubicación original. No se copió material de licencia
incierta ni se asumió permiso de redistribución. G1 arquero: Unitree Robotics,
BSD-3-Clause en unitree_mujoco/LICENSE; atribuciones de FreeKick conservadas en
documentación anterior. {audit['external_files_checked']} archivos externos cotejados
contra hashes de Fase 2; ninguno cambiado. Cada episodio verificó también los 21
fuentes Python previos. Las comprobaciones y hashes del código propio están en audit.json.
'''
    output.write_text(text,encoding='utf-8')
    print(str(output))

if __name__=='__main__':main()
