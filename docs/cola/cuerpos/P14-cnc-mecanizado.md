# P14 — CNC y mecanizado: veredictos honestos por máquina, tarjetas de operación y tabla de herramientas

**Depende de:** P01, P02 y P12 (pestaña Mecanizado del detalle de OT).

## Objetivo
Que nadie cargue un programa a una máquina sin saber **exactamente** qué va a hacer, qué no se emitió y por qué. Y que lo desconocido bloquee, no se adivine.

## Situación actual
- Motor en `engine/src/dekopen_engine/operations.py` y `manufacturing.py`; backend en `backend/production` (programas y máquinas).
- La fase 14 verificó: programa en CNC-01 con WARN `feature_point_only`, bloqueo 422 `cnc_program_blocked` en CNC-SAW y manifiesto verificado por hash.
- (auditoría, sesiones 9bb78bdc y fde66b2e)
  - Matriz de veredictos para 6 máquinas (Bloqueado/Atención), buena idea pero densa.
  - Tabla de máquinas en texto denso.
  - La tabla de operaciones filtra enums.
  - Hay operaciones **declaradas pero no emitidas**: drenaje, preparación de cerradura, de bisagra, puntos de cierre y acopladores.
  - El programa queda “reemplazado” después de reoptimizar.
- `docs/wiki/quality/known-risks.md` (sección CNC): sistema de coordenadas, unidades, cara, lateralidad, herramientas, profundidad, colisión con mordazas, bloqueo de operaciones no soportadas, orientación de la sección y determinismo. **“Never best-guess machine data.”**

## Alcance
1. **Tarjeta por miembro:** perfil (SKU humano, rol en español y largo), vista de la cara a escala con las operaciones dibujadas desde el **datum declarado** (origen y cara marcados) y la lista de operaciones: tipo en español, cara, X desde el datum, Y/Z si aplica, profundidad, herramienta y fuente de la regla.
2. **Veredicto por máquina** PASS / WARN / BLOCK con motivos legibles (“Herramienta para ‘preparación de cerradura’ no declarada en CNC-02”). BLOCK cuando falta una herramienta, una coordenada, una mordaza o una orientación: **nunca un valor por defecto**.
3. **“Operaciones declaradas no emitidas”**, como sección explícita por OT y por máquina, con la causa de cada una (sin regla, sin herramienta, emisor no implementado). Si el emisor no existe, se dice así; no se oculta.
4. **Máquinas y herramientas:** CRUD por organización (solo OWNER y WORKSHOP_MANAGER, con RLS) de máquinas (tipo, ejes, carrera, mordazas declaradas) y de la tabla **código de herramienta ↔ tipo de operación**, que es la autoridad. Auditoría de los cambios. Corrige que las actualizaciones devuelvan la fila actualizada (auditoría: “update operations correctly return updated rows”).
5. **Programas:** incluyen la huella del plan y la semilla de optimización; si se reoptimiza, el programa anterior queda “Reemplazado” con un enlace al vigente; descarga del manifiesto con hash.

## Fuera de alcance
Postprocesadores nuevos para formatos propietarios. **No inventes formatos de máquina**: si no hay un postprocesador declarado, el veredicto es BLOCK con esa causa.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El programador CNC y el jefe de taller. Debe sentir: “sé exactamente qué va a hacer la máquina”.
- **Anatomía:** Vista de programa con operaciones emitidas y **no emitidas** igual de visibles; BLOCK con causa; CRUD de herramientas en `DataTable`.
- **Momento de firma (preservar o crear):** F7: lo que requiere decisión humana se marca en naranja, nunca se adivina.
- **Idea que sube el techo (obligatoria, con el motor):** Vista previa del perfil con cada operación ubicada sobre su sección, y diff entre la versión del programa y la anterior antes de enviarlo.
- **Slop a eliminar aquí:** Advertencias genéricas, operaciones ocultas, programas descargables sin explicar qué incluyen.
- **Preguntas del pase editorial:** ¿Algo desconocido puede llegar a la máquina sin bloquear? ¿El operador entiende por qué se bloqueó?

## Criterios de aceptación
- Tests del motor con fixtures de máquina: falta de herramienta → BLOCK; operación sin emisor → aparece en “declaradas no emitidas”; misma entrada → mismo programa (hash) dos veces.
- Test de RLS y permisos del CRUD de máquinas y herramientas (`make test-db`).
- UI sin enums (`ux:capture`) y capturas de la tarjeta de miembro y de la matriz de veredictos.
