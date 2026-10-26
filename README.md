# RoboPenalty AI

Proyecto académico de IA para UADE: penales físicos entre dos humanoides G1 en MuJoCo. Versión interactiva: **phase9a**; base nominal: **phase8c**; estadio: **phase7d**. Launcher público: **run_robopenalty.py**.

## Estado

Funcional en la instalación validada: simulación física, FreeKick ONNX externo, arquero autónomo con predictor/planificador B, cinco tiros calibrados, postura dinámica, estadio, marcador, tanda de cinco, modo automático y modo dirigido por texto.

**La voz todavía no funciona de forma confiable y no está validada. La ejecución en otras computadoras tampoco está validada.** No se incluyen grabaciones, transcripciones ni información de dispositivos.

## Arquitectura

Entrada → normalización/parser estricto → cola con ticket → orquestador en el hilo físico. El delantero elige por utilidad o recibe una selección manual. El arquero recibe solo observaciones físicas actuales, nunca la orden, el preset ni el futuro. Un único estado MuJoCo determina contactos y resultados; el estadio solo lo presenta. La capa portability adapta recursos y hashes, sin cambiar robots, política, agentes o aprendizaje.

Tecnologías: Python 3.12, MuJoCo, NumPy, ONNX Runtime, Hydra/OmegaConf, PyYAML y auxiliares. Voz experimental local y opcional, desactivada por defecto.

## Descargar y preparar

```powershell
git clone https://github.com/agreboyras/RoboPenalty-AI.git RoboPenalty
Set-Location .\RoboPenalty
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

Es una guía de instalación **pendiente de validar en otra PC**, no una promesa de ejecución autónoma. Los pines reflejan el entorno observado.

Se necesitan carpetas hermanas con recursos autorizados:

```text
trabajo/
  RoboPenalty/
  RoboNaldo_Deploy/
  unitree_mujoco/
```

**FreeKick, ONNX, NPZ, MJCF y meshes externos no están incluidos.** La instalación adaptada de Deploy puede diferir del upstream limpio. El manifiesto público exige 209 hashes exactos: rechaza faltantes o diferencias. No desactivar comprobaciones para arrancar. Ver [dependencias](docs/DEPENDENCIAS_EXTERNAS.md) y [atribuciones](THIRD_PARTY.md). Clonar este repositorio por sí solo no basta.

## Ejecutar

Desde la raíz, usar un intérprete con las dependencias:

```powershell
$env:PYTHONUTF8 = '1'
$py = '.\.venv\Scripts\python.exe'
# En la instalación previa puede reutilizarse:
# $py = '..\RoboNaldo_Deploy\.venv-robonaldo\Scripts\python.exe'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
```

Automático: cinco penales, semilla 2026, distancia 6 m, postura dinámica y aprendizaje entre episodios:

```powershell
& $py -B .\run_robopenalty.py --viewer --mode auto --autostart --once --output ".\phase9a\results\auto_$stamp"
```

Dirigido por texto:

```powershell
& $py -B .\run_robopenalty.py --viewer --mode directed --once --output ".\phase9a\results\dirigido_$stamp"
```

Escribir **Iniciar partido**, esperar READY PARA ELEGIR y dar una orden por penal:

| Ejemplo escrito | Acción de 8C | Bias |
|---|---|---:|
| Pateá al centro | center | 0 |
| Tirá a la izquierda | left_near_b060, centro-izquierda | +0,60 |
| Patea a la derecha | right_inter_m080 | −0,80 |
| Dispará a la derecha abierta | right_open_m100 | −1,00 |
| Pateá a la esquina derecha | right_corner_m140 | −1,40 |

Estos son ejemplos de comandos, no transcripciones. No existe esquina izquierda robusta en 8C. La trayectoria depende del contacto; no se promete un punto exacto. Se rechazan frases ambiguas y órdenes durante otra patada, sin fallback. Los tiros manuales no actualizan estadísticas automáticas.

Comandos: ayuda, estado, mostrar marcador, pausar partida, reanudar partida, modo automatico, modo dirigido, reiniciar partido, salir. Cambios/reinicio requieren estados seguros. Salir durante un tiro permite terminarlo; durante selección sale sin puntuar un penal inexistente. Omitir --once conserva la sesión al finalizar.

Cámaras: /cam behind, /cam overview, /cam goal, /cam execution, /cam follow. Omitir --viewer para headless; --no-decoration desactiva decoración. La espera sincroniza el visor sin avanzar física. Cada salida debe ser una carpeta nueva dentro de phase9a.

## Tests y privacidad

```powershell
& $py -B -m unittest discover -s .\portability -p 'test_*.py'
& $py -B -m unittest discover -s .\phase9a -p 'test_*.py'
```

Los tests ASR con dobles no validan micrófono real. El directorio de modelo solo contiene un aviso propio para fixtures; no incluye pesos. La voz no es un control recomendado para la entrega.

Se conserva código histórico seguro, configuraciones y 48 calibraciones obligatorias sin cambiar bytes. Se excluyen registros, información de dispositivos, documentos con datos locales y los 15 ZIP, que siguen solo en la computadora original. Algunos análisis archivísticos requieren sus archivos locales excluidos. La ejecución normal no necesita ese baseline privado. Ver [portabilidad y validación](portability/README.md).

.gitignore es una lista de inclusión explícita: revisar nuevos archivos antes de ampliarla. No agregar resultados crudos por fuerza. Mantener ramas por cambio y no editar fases históricas para nuevas variantes.

Fases: 2 dos robots; 3A/3B guía/predictor; 4A/4B tiros/utilidad; 5 tanda; 6A/6B visor/voz experimental; 7B/7C/7D escenario; 8B.1/8B.2/8B.3 planificación/tiros/postura; 8C consolidación; 9A interacción.

Límites: arquero restringido a guía, sin locomoción libre; postes/red visuales; gol con criterio histórico del centro de la pelota; robustez nominal/discreta, no global. Pendientes: instalación limpia, acceso autorizado a dependencias, voz, pruebas adicionales y acuerdo de licencia del código propio.

