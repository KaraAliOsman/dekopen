# ED2 — Pase editorial de la ola 2: el editor implacable revisa todo lo construido y elimina lo arbitrario

**Depende de:** todos los encargos de la ola 2 mergeados en `integracion/v1` (P06, P08, P11, P13, P14, P15, P16) y ED1. **No corre en paralelo con nada.** Adjunta: `CONSTITUCION-DISENO.md`.

## Por qué existe este encargo
Producir es barato; por eso la calidad se filtra al final. Cada PR de la ola hizo su propio pase editorial, pero **nadie miró el conjunto**: siete encargos en paralelo producen nueve criterios ligeramente distintos, componentes duplicados, términos que no coinciden y momentos que se pisan. Este encargo es el editor: se responsabiliza de cada decisión visible del producto tal como quedó, y deja la ola **coherente, singular y sin slop** antes de construir encima.

**No agrega funcionalidades.** Corrige, unifica, quita y pule. Si encuentra una funcionalidad rota, la arregla.

## Superficies en revisión
Bow y acoplados en el editor (P06) · Emisión de cotización y estado del enlace (P08) · Cobranza y facturación (P11) · Pack de corte y etiquetas (P13) · CNC (P14) · Compras e inventario (P15) · Catálogo e ingesta por IA (P16 + D01) · **y la continuidad con todo lo revisado en ED1** (las decisiones editoriales de ED1 en `docs/wiki/log.md` son vinculantes).

## Alcance
1. **Recorrido por persona** (constitución §1.2) con el fixture de P00: un día del estimador (proyecto de 12 posiciones con bow → precio → emisión → seguimiento del enlace), del dueño (cobranza → catálogo: subir una ficha PDF y revisarla), del jefe de compras (comprar lo que falta → recepción parcial → retazos) y del jefe de taller y el cortador (pack de corte → etiquetas → CNC). Capturas en 1440 claro y oscuro, 1024 y 390 donde aplique.
2. **Rúbrica R1–R20 por superficie** con la tabla PASA/FALLA. Todo FALLA se corrige en este PR.
3. **Coherencia entre superficies** (la parte que ningún PR individual pudo ver):
   - un solo componente por función: si hay dos tablas, dos selectores de apertura, dos chips de estado o dos formateadores que hacen lo mismo, deja uno y borra el otro;
   - el mismo término para lo mismo en todas partes (glosario §4);
   - el mismo formato para la misma magnitud (§3.3) en pantalla, PDF y etiqueta;
   - la misma simbología de apertura en lienzo, ícono, DOC-01 y Orb/artefactos;
   - espaciado equivalente entre secciones equivalentes;
   - una sola acción principal por región en todo el recorrido.
4. **Caza de slop** (constitución §9.4) en todas las superficies: grillas de tarjetas que no son colecciones, KPI sin decisión, copy genérico, íconos de relleno, explicaciones redundantes, modales evitables, "Próximamente". Lista lo que quitaste y por qué.
5. **Momentos de firma:** verifica que cada superficie conserva el suyo (§7) y que no se diluyeron (por ejemplo, el naranja usado fuera de su significado, ingletes repetidos o el Orb animado sin trabajo real).
6. **Ideas que suben el techo:** prueba cada idea del §8 implementada en la ola con el motor real. Si alguna quedó como maqueta, termínala.
7. **Tres veces mejor:** al terminar, identifica las 5 cosas más débiles del producto en su estado actual y mejóralas. Luego repite una vez más con las 3 que queden.
8. **Guardas:** baja la línea base de las guardas de P01 en todo lo que toques y reporta el delta.

## Fuera de alcance
Funcionalidades nuevas, cambios de dominio y superficies de la ola 3 (las revisa el pase editorial final de P20).

## Criterios de aceptación
- Tabla de rúbrica por superficie, toda en PASA, en el PR.
- Lista de duplicados eliminados (componentes, CSS, formateadores, términos) con el antes y el después.
- `ux:capture` completo de las superficies de la ola: 0 hallazgos de slop y 0 críticos; delta de la línea base de guardas.
- Capturas "antes de ED2" y "después de ED2" de cada recorrido por persona, lado a lado, en `docs/redesign/captures/ed2/`.
- Nota en `docs/wiki/log.md` con las decisiones editoriales tomadas, para que la ola 3 las respete.
