# Validación del paquete público — 26/10/2026

- **251 tests, 29 suites, aprobados** en una copia con solo archivos públicos y sin el baseline privado. Incluye 247 tests existentes y 4 nuevos de rutas, hashes estrictos, recursos faltantes, traversal y alcance del adaptador.
- Se ejecutaron cinco penales dirigidos por el launcher público. Acciones: right_inter_m080, right_open_m100, right_corner_m140, left_near_b060, center. Resultado: GOAL, GOAL, GOAL, SAVE, SAVE; 35.000 pasos, aproximadamente 70 s simulados.
- Igualdad **exacta, sin tolerancias**, frente a la referencia nominal 8C: estados iniciales/finales de integración, evaluación/contactos, trazas, trayectorias registradas, decisiones del arquero, postura, retorno y monitor de motores. No se comparó solamente el marcador.
- Las esperas de selección y la pausa conservaron el estado completo. Cinco registros manuales y ninguna actualización del aprendizaje automático. El selector automático conserva sus tests de equivalencia.
- El experimento histórico 4A actual, ejecutado por su entrypoint original y por el adaptador, dio igualdad exacta de estado inicial, configuración, evaluación, guía, trazas y agente bajo condiciones idénticas.
- Una referencia archivada anterior de ese experimento estaciona al arquero a Y=3 m; el código actual lo hace a Y=8 m. No se declara igualdad entre esas condiciones ni se cambió el registro o el código histórico. Esta limitación archivística no apareció en la comparación nominal 8C/9A.
- La copia aislada reutiliza el mismo intérprete y los recursos externos autorizados mediante enlaces locales. **No es una instalación limpia ni demuestra ejecución en otra computadora.** No se hizo una nueva prueba de visor ni de micrófono para esta publicación.
- Los tests de voz usan dobles/fixtures: **la voz continúa sin funcionamiento confiable validado**. No se publican grabaciones, transcripciones ni datos de dispositivos reales.
- Se conservan sin cambios las 220 fuentes históricas protegidas y los 15 ZIP locales. Los originales privados no se modificaron ni se publican.

Solo se incluyen 48 calibraciones obligatorias, una referencia numérica para tests visuales y un fixture de articulaciones, revisados como datos de simulación; no son registros de micrófono ni recursos 3D de terceros. Los resultados nuevos quedan fuera de Git por defecto.
