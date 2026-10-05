# P18 — Desempeño térmico y normativa chilena: Uw, clase de permeabilidad al aire y zona térmica (OGUC 4.1.10)

**Depende de:** P16 (procedencia del catálogo). Opcional: P09 para el anexo técnico del DOC-01.

## Objetivo
Diferenciar a DEKOPEN en Chile: que cada posición muestre su **Uw** y su **clase de permeabilidad al aire** cuando existan datos autoritativos, y que el proyecto diga si cumple la reglamentación térmica vigente para su zona. **Sin datos certificados, no hay afirmación de cumplimiento.**

## Contexto externo (fuentes públicas; verifica los textos oficiales antes de codificar tablas)
- La actualización del art. 4.1.10 de la OGUC se publicó en el D.O. el 27-05-2024 y **rige desde el 28-11-2025**. Aplica a uso residencial y a equipamiento de educación y salud. Usa **9 zonas térmicas (A–I)**; fija un porcentaje máximo de ventanas según orientación y valor U de la ventana; exige una **clase mínima de permeabilidad al aire para puertas y ventanas, medida a 100 Pa, según zona**; y en zonas B a I las ventanas en techumbre deben tener U ≤ 3,6 W/m²K. Fuentes: minvu.gob.cl/nueva-reglamentacion-termica, la presentación “Puertas y Ventanas” de DITEC (nov. 2025) y el Diario Oficial del 27-05-2024.
- Normas de ensayo: NCh 888 (requisitos básicos), NCh 889 (mecánicos), NCh 890 (viento), NCh 891 (estanquidad al agua) y NCh 892 (estanquidad al aire).
- El sector ya muestra U y g en la cotización; por ejemplo, Windowmaker calcula U y g según EN 14351-1 y los incluye en la cotización y en un reporte térmico.

## Alcance
1. **Modelo de datos con procedencia:**
   - Por sistema y perfil: Uf (W/m²K) por combinación de perfiles si el fabricante la declara.
   - Por vidrio: Ug y factor g.
   - Por separador: Ψg (W/mK).
   - Por sistema: clases de aire, agua y viento con el informe de ensayo (documento, laboratorio, fecha y alcance de dimensiones ensayadas).
   - Todo con procedencia y revisor (P16). Los valores DEMO quedan marcados como sintéticos.
2. **Motor:** Uw según el método de áreas de ISO 10077-1, `Uw = (Ag·Ug + Af·Uf + lg·Ψg) / (Ag + Af)`, con Ag, Af y lg tomados de **la geometría del motor**. Si falta cualquier entrada autoritativa, el resultado es UNKNOWN con la lista de lo que falta. Golden tests con casos calculados a mano y documentados en el test.
3. **Proyecto:** campo de zona térmica (A–I). Mapeo comuna → zona solo si se importa la tabla oficial como archivo de datos con su fuente citada; si no, lo elige el usuario. Orientación por posición (N, O-P, S u OGT), opcional.
4. **Panel de cumplimiento** del proyecto, por posición: Uw, clase de aire y, frente a la zona, la exigencia de clase mínima de aire y la tabla de porcentaje máximo por orientación y U. Las tablas se codifican **solo** desde el texto oficial, con test de transcripción y cita. Resultado: Cumple, No cumple o Sin datos suficientes, con la causa. Aclara en la UI que el cumplimiento del porcentaje de ventanas depende de la superficie de muro, que DEKOPEN no conoce, salvo que el usuario la ingrese.
5. **Documento:** anexo técnico opcional en el DOC-01 (P09) con Uw y clases por posición, **solo** si son autoritativos.

## Fuera de alcance
Simulación térmica avanzada (ISO 10077-2, elementos finitos); certificación.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** El estimador y el cliente que necesita cumplir la OGUC. Debe sentir: “sé si cumple y por qué”.
- **Anatomía:** Uw y clase de aire en la ficha de la posición con `TraceButton`; veredicto del proyecto por zona, con la fuente normativa citada.
- **Momento de firma (preservar o crear):** F6: el Uw explica de qué Uf, Ug y Ψ sale y de qué certificado viene cada uno.
- **Idea que sube el techo (obligatoria, con el motor):** Si una posición no cumple, propone la alternativa más barata que sí cumple (otro vidrio o sistema del catálogo) con su Δ de precio.
- **Slop a eliminar aquí:** Afirmaciones de cumplimiento con datos DEMO, semáforos sin causa, valores sin fuente.
- **Preguntas del pase editorial:** ¿Es imposible afirmar cumplimiento sin datos certificados? ¿La propuesta alternativa sale del motor?

## Criterios de aceptación
- Golden tests de Uw en el motor (Decimal, mismas áreas que la geometría).
- Test de que cualquier entrada faltante produce UNKNOWN y no un número.
- Test de que las tablas transcritas coinciden con el texto oficial (fixture con la cita).
- Capturas del panel de cumplimiento con datos completos, incompletos y DEMO.
