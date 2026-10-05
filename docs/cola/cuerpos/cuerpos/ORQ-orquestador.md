# ORQ — Orquestador del programa DEKOPEN v1: ejecuta la cola completa de punta a punta

**Para qué:** el dueño quiere que la IA haga absolutamente todo y le entregue el producto 100 % listo para revisar. Este prompt te convierte en **líder técnico del programa**: ejecutas los 39 encargos de la cola en el orden correcto, controlas la calidad entre olas y terminas con un único PR hacia `main` que el dueño revisa. Trabajas con **Codex local**: la cola completa ya está copiada en **`docs/cola/`** del clon (`prompts/`, `cuerpos/`, `CONSTITUCION-DISENO.md`, `00-LEEME.md` y `adjuntos/`).

## 0. Dos formas de correr este programa
- **Con el script `ejecutar-cola.ps1` (lo normal).** El script lanza **una sesión de Codex nueva por encargo**, en el orden del §2, y te indica al inicio cuál es tu encargo (`ENCARGO ACTUAL: <ID>`). En ese caso **haces solo ese encargo**, de punta a punta, siguiendo el §3 y el §4, y terminas. El script lee `docs/cola/ESTADO.md` para saber si puede pasar al siguiente: deja tu fila en `mergeado` (o `bloqueado`, con la causa) antes de terminar.
- **Pegado directo en una sesión interactiva de Codex.** Entonces ejecutas tú la cola entera en serie, en el orden del §2, releyendo cada prompt completo antes de empezarlo.

## 1. Preparación (solo la primera vez, antes de P00)
1. Lee `docs/cola/00-LEEME.md`, `docs/cola/CONSTITUCION-DISENO.md` y `docs/cola/cuerpos/_contrato.md` completos antes de hacer nada.
2. Ejecuta **P00** tal como está escrito (crea `integracion/v1`, commitea la constitución y los registros).
3. En el mismo PR de P00 commitea la cola bajo **`docs/cola/`** tal como está (~21 MB con `adjuntos/`). **No commitees ningún `.env` ni secretos** (`docs/cola/` no contiene ninguno; verifícalo antes de commitear). Así cada sesión siguiente relee su encargo y sus adjuntos desde el repo.
4. Crea **`docs/cola/ESTADO.md`**: una tabla con una fila por encargo, con este formato exacto de columnas: `| ID | Ola | Estado | PR | SHA | Notas |`, y `Estado` ∈ `pendiente` / `en curso` / `mergeado` / `bloqueado`. Actualízala al empezar y al terminar cada encargo (commit directo a `integracion/v1` con mensaje `cola: estado <ID>`). Es la memoria del programa.

## 2. Orden de ejecución
| Ola | Encargos | Puerta de salida |
|---|---|---|
| 0 | **P00** | `integracion/v1` existe; constitución, `docs/cola/` y `ESTADO.md` en el repo |
| 0b | P01 · IA1 · D01 | Tokens y guardas activos; línea base de la IA medida; sistemas, ingesta y catálogo demo |
| D1 | D02 · D03 · D04 | Vidrio, aperturas y herrajes estructurados en el motor |
| D2 | D05 · D06 · D07 · IA2 · IA3 | Dominio completo; IA con operaciones tipadas y proveedor real |
| 1 | P02 · P03 · P04 · P05 · P07 · P09 · P12 · P17 · P25 | Superficies núcleo rediseñadas |
| **ED1** | Pase editorial de la ola 1 | Rúbrica en PASA en todo lo construido |
| 2 | P06 · P08 · P11 · P13 · P14 · P15 · P16 | Flujos comerciales y de planta completos |
| **ED2** | Pase editorial de la ola 2 | Rúbrica en PASA, coherencia con ED1 |
| 3 | D08 · P10 · P18 · P19 · P21 · P22 · P23 | Superficies restantes |
| 4 | P24 | Analítica sobre datos reales del flujo |
| 5 | **P20** | Aceptación final y PR `integracion/v1` → `main` |

Se ejecutan **en serie**, en este orden exacto (respeta los archivos con riesgo de conflicto del §4 del LEEME): P00, P01, IA1, D01, D02, D03, D04, D05, D06, D07, IA2, IA3, P02, P25, P04, P05, P09, P07, P03, P12, P17, ED1, P06, P08, P13, P15, P11, P14, P16, ED2, P21, P10, P22, P23, D08, P19, P18, P24, P20. **Un encargo empieza solo cuando el anterior está mergeado en `integracion/v1` con CI en verde** (o `bloqueado` con su causa).

## 3. Cómo ejecutar cada encargo
1. `git fetch` y actualiza `integracion/v1`. Marca la fila `en curso` en `ESTADO.md`.
2. **Lee completos** `docs/cola/prompts/<ID>.md` (trae el contrato) y la constitución. No trabajes de memoria ni con resúmenes.
3. Crea la rama `codex/<ID>-<slug>` desde `integracion/v1`. Cumple el encargo **entero**: código, migraciones, tests, OpenAPI y orval si cambia la API, wiki.
4. Levanta el stack local (skill `testing-framedex`; carga el `.env` de la raíz en el entorno del proceso) y verifica el flujo con Playwright en los tamaños y temas del contrato. Guarda las capturas.
5. Haz el pase editorial (constitución §9) y deja la rúbrica R1–R20 en el PR.
6. `gh pr create --base integracion/v1`. Espera los 4 checks (`gh pr checks --watch`); si algo falla, corrígelo en la misma rama hasta que estén en verde. No debilites ningún check.
7. `gh pr merge --squash --delete-branch`. Registra PR y SHA en `ESTADO.md`, fila en `mergeado`.

Un encargo, una rama, un PR. Nunca mezcles dos encargos en un PR.

## 4. Reglas del orquestador
- **Calidad antes que velocidad.** No acortes ningún encargo para avanzar más rápido. Si un encargo deja algo a medias, no lo marques `mergeado`: termínalo.
- **Coherencia del programa.** Antes de cada encargo, relee las decisiones registradas en `docs/wiki/log.md` y `docs/decisions/valores-por-defecto.md`; respétalas.
- **Conflictos:** rebasea sobre `integracion/v1` antes de abrir y antes de mergear el PR.
- **Bloqueos reales** (contrato, “Detente solo si”): marca `bloqueado` en `ESTADO.md` con la causa, haz todo lo que no dependa del bloqueo y deja el resto aislado. Las integraciones diferidas (Railway, Flow, SII, correo) **no son bloqueos**.
- **Nunca** mergees a `main`, nunca imprimas ni commitees secretos (el `.env` jamás entra a git), nunca debilites un check de CI, nunca hagas `push --force` sobre `integracion/v1` ni `main`.
- **Informe de avance:** al cerrar cada ola, agrega a `ESTADO.md` un resumen de 5 líneas (qué quedó, capturas clave, riesgos).

## 5. Entrega
El programa termina cuando P20 abre el PR `integracion/v1` → `main` con los 4 checks en verde, `docs/GUIA-REVISION.md` probada y `ESTADO.md` con todos los encargos en `mergeado`. Último mensaje (de P20, o tuyo si corres la cola entera): enlace al PR final, la tabla de `ESTADO.md`, el informe de aceptación y la lista de lo que el dueño debe conectar (de `ACTIVACION.md`).

## Criterios de aceptación
- Los 39 encargos en `mergeado` en `ESTADO.md`, cada uno con su PR y su SHA (o `bloqueado` con causa y lo que se hizo alrededor).
- ED1, ED2 y el pase editorial de P20 documentados con su rúbrica en PASA.
- PR final hacia `main` abierto y sin mergear.
