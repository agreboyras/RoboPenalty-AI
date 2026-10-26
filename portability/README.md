# Capa mínima de portabilidad

4A lee del baseline de phase2 únicamente external_inputs.files_sha256. Usa sus claves como rutas y verifica SHA-256 antes/después de simular. 3A/3B consumen el mismo mapa. No usa resultados físicos ni datos de audio de ese registro. Es una dependencia de integridad externa.

external_manifest.json conserva los 209 hashes con raíz permitida y ruta relativa, generados tras comprobar los archivos reales. No contiene raíces personales. No se relajan checksums ni se inventan rutas.

El launcher público selecciona una subclase del runtime. Verifica recursos antes de construir robots y asigna Path/HOME solo al módulo privado del runner. La lectura exacta del baseline se resuelve en memoria con el mapa real verificado; otras lecturas se delegan a pathlib. No crea un resultado físico falso, no escribe el original y no modifica pathlib global, política, física, agentes o aprendizaje.

Los launchers históricos directos permanecen como estaban. Una prueba explícita de 4A:

```powershell
& .\.venv\Scripts\python.exe -B .\portability\run_historical.py --phase phase4a --scenario long_center --mode probe --output .\phase9a\results\historico_nuevo.json
```

La salida debe ser nueva. Los análisis que requieren otros resultados archivados siguen siendo tareas locales separadas.

Publicación: código seguro, documentación pública y calibraciones obligatorias idénticas por hash. Se excluyen registros, transcripciones, información de dispositivos, documentos históricos con datos locales y ZIP. Los ejemplos de fixtures son escritos para tests.

La copia pública aislada se valida usando el mismo entorno y recursos externos autorizados; esto no equivale a una instalación limpia ni demuestra ejecución en otra computadora. La voz continúa pendiente. El escaneo por patrones no garantiza ausencia absoluta de secretos.

