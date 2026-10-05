# P06 — Bow/bay y conjuntos acoplados dentro del editor principal

**Depende de:** P04 (layout del editor) y P05 (contrato de dibujo).

## Objetivo
Que un ventanal bow de 3 módulos o un conjunto acoplado (por ejemplo, puerta + lateral fijo + sobreluz) se diseñe en **el mismo editor** que una ventana simple, con la planta y la elevación sincronizadas, los ángulos editables sobre la planta y acopladores que solo se ofrecen si son compatibles según el catálogo.

## Situación actual
- Archivos: `frontend/src/features/canvas/AssemblyEditor.tsx`, `BowPlanSvg.tsx`, `assemblyCommands.ts`, `assemblyGraph.ts` y `useAssemblyCalculation.ts`. Motor: composición de ensamblajes, módulos y acoples. `docs/PRODUCT.md` dice que bow/bay son plantillas sobre la composición, **no ramas de enum**.
- (auditoría, sesión f5305cc9 y otras) Es un formulario aparte (“Tipo de producto: Ventana bow / conjunto”) con una tabla de módulos (Ancho / Apertura / Vidrio / Panel), una tabla de uniones (Ángulo / Acoplador COPLE-60 o COPLE-90) y una polilínea de planta gruesa. Con ángulos de 89° la planta queda en U sin advertencia clara. Aparece “No pudimos calcular el conjunto. Revisa los datos.” sin decir qué dato. La elevación frontal sale como mosaicos separados.

## Diseño objetivo
- En el editor de P04 aparece una **vista Planta acoplada** bajo la elevación, de altura ajustable, cuando el producto es un conjunto. Seleccionar un módulo en la planta lo selecciona en la elevación, y al revés.
- **Ángulo** editable sobre la planta: manija en la unión, arrastre con snapping a 0, 10, 15, 22,5, 30, 45 y 90°, e input numérico al hacer clic. El acoplador se elige de una lista filtrada por compatibilidad de ángulo y sistema **desde el catálogo**. COPLE-60/90 son DEMO: no las asumas en código.
- **Cotas de conjunto**, siempre etiquetadas y explícitas: “Ancho desarrollado” (suma de módulos + acopladores), “Frente / cuerda” (proyección), “Proyección” (salida del bow) y la altura.
- Selector de elevación: “Desarrollada” (módulos uno al lado del otro) o “Proyectada” (vista real de frente con escorzo).
- Mensajes en lenguaje de taller, accionables y con enlace al campo, por ejemplo: “El acoplador COPLE-60 admite de 0° a 60°; con 89° elige un acoplador de 90° o reduce el ángulo”.
- **Precio** por módulo y total del conjunto en el chip de precio (motor).
- Plantillas en la biblioteca: “Bow 3 módulos”, “Bay 3 módulos 45°”, “Puerta + lateral fijo”, “Ventana + sobreluz” y “Esquina 90°”, todas construidas con la misma composición del motor.

## Fuera de alcance
3D del conjunto (P19); documentos (P09 ya consume la planta si existe).

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador que cotiza un bow o un conjunto acoplado. Debe sentir: “es igual de fácil que una ventana simple”.
- **Anatomía:** Mismo editor de P04: planta y elevación sincronizadas, ángulos editables sobre la planta, acopladores ofrecidos solo si el catálogo los hace compatibles.
- **Momento de firma (preservar o crear):** F4 aplicada a ángulos: el ángulo se edita en la planta, donde se lee.
- **Idea que sube el techo (obligatoria, con el motor):** Arrastrar un módulo en la planta recalcula ángulos, acopladores y precio en vivo, con la incompatibilidad explicada en el lugar exacto si aparece.
- **Slop a eliminar aquí:** Un formulario aparte para bow, errores genéricos (“configuración inválida”), ángulos como campos sueltos sin dibujo.
- **Preguntas del pase editorial:** ¿Un bow de 3 módulos se arma en menos de 1 minuto? ¿Cada error dice qué módulo y qué hacer?

## Criterios de aceptación
- e2e: crear un bow de 3 módulos (central fijo de 1200, laterales abatibles de 600, ángulos de 2 × 22,5°) en ≤ 10 interacciones; guardar, reabrir y verificar que es idéntico (test de igualdad del modelo).
- La planta y la elevación quedan sincronizadas en la selección y en las medidas (test).
- Test del motor: compatibilidad ángulo ↔ acoplador desde fixtures de catálogo; sin ramas nuevas de enum.
- Los mensajes de error identifican el campo exacto (test por cada error del motor relevante).
- El DOC-01 de un proyecto con bow muestra planta + elevación desarrollada (captura).
