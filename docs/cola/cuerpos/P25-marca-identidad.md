# P25 — Marca e identidad: la sección de perfil como firma, del favicon al correo

**Depende de:** P01 (tokens, Plex, íconos). Ola 1, en paralelo con el resto. Adjunta: `CONSTITUCION-DISENO.md`, `diseno/board-02-mark-studies.png`, `diseno/dekopen-visual-identity-study.md`, `bot/*`.

## Objetivo
Que DEKOPEN tenga una identidad **extraída de su propio producto** y aplicada con disciplina en cada punto de contacto: la marca, el favicon, el ícono de la app, el login y el onboarding, los correos transaccionales, los estados vacíos, el bloqueo de documentos y la relación con el Orb. Y que la marca **se retire** donde manda la del fabricante (documentos y portal del cliente son white-label).

## Por qué
Hoy no hay una marca aplicada de forma consistente: el estudio de identidad propuso cuatro direcciones y recomendó una, pero nada se implementó. Los puntos de contacto que no son pantallas de trabajo (login, correos, favicon, estados vacíos) son justamente donde un producto parece demo o parece serio.

## Decisión de marca (constitución §11)
- **Marca principal: dirección B, “La sección”.** Anillo cuadrado (el corte de un perfil hueco extruido) con un tabique interno a 1/3 del ancho; exterior 24 × 24, radio r-1, pared 2,5, tabique 2. La sección **reemplaza la O** del logotipo: `DEK⧈PEN`. Logotipo en Plex Sans SemiBold, mayúsculas, tracking +0,06 em, g-950 (g-25 sobre oscuro). Nunca degradado, contorno ni efectos.
- **Bloqueo de documento: dirección D, “La cota”** (el logotipo enmarcado por una línea de cota con ticks a 45°), solo para la portada interna, la página “Acerca de” y los correos.
- **La gramática de aperturas (dirección C)** queda para los íconos, no para la marca.
- **Asistente:** “Asistente DEKOPEN” con el Orb (spec `bot/dekopen-orb-spec.md`). No se usa “STARWIN”. Verifica que el Orb actual (`Orb.tsx`, `BotFigure.tsx`) es coherente con la paleta y la forma de la marca (grafito, teal, una órbita); si no, ajústalo sin cambiar su API.

## Alcance
1. **Archivos de marca** en `frontend/src/brand/` como SVG optimizados y componentes React (`<BrandMark size>`, `<Wordmark>`, `<DocLockup>`), con construcción geométrica documentada en `docs/design/marca.md` (grilla, proporciones, zona de protección, tamaños mínimos: marca 16 px, logotipo 72 px) y usos prohibidos con ejemplos.
2. **Favicon y ícono de la app:** SVG + PNG 16/32/180/192/512 + `manifest.webmanifest` (nombre, colores de tema teal-800 y g-50). Variantes para tema claro y oscuro.
3. **Login, magic link y onboarding:** pantalla de entrada como **hoja técnica** (superficie paper con inglete sobre la mesa g-50, marca, una sola acción) en densidad `office`, perfecta a 390 px. El onboarding sigue la constitución: preguntas mínimas, cada paso con su porqué, progreso como `Stepper`, y termina en la primera posición dibujada (no en un dashboard vacío).
4. **Correos transaccionales** (magic link, cotización enviada al cliente, aprobación recibida, pago registrado, OT bloqueada): plantillas HTML compatibles con clientes de correo, white-label cuando el destinatario es el cliente final (marca y colores de la organización del fabricante; DEKOPEN no aparece), y con la marca DEKOPEN solo en los correos internos. Texto en español con la voz del §4 (usted hacia el cliente). Vista previa en `/dev/correos`. El envío real con dominio propio es integración diferida: deja el adaptador y la sección en `ACTIVACION.md`.
5. **Estados vacíos con lenguaje de dibujo:** en vez de ilustraciones genéricas, una pequeña **lámina** con el dibujo técnico de lo que falta (una elevación vacía con cotas fantasma para “sin posiciones”, una barra sin cortes para “sin plan de corte”), trazada con los tokens del lienzo. Componente `EmptyIllustration kind` reutilizable por `EmptyState`.
6. **Página 404/500 y “sin conexión”:** con la misma lámina y una acción.
7. **White-label en los entregables del cliente:** DOC-01, portal y correos al cliente usan la marca de la organización (logo, color primario validado por contraste AA contra paper; si no pasa, se usa teal-800 y se avisa en Ajustes). “Generado con DEKOPEN” oculto por defecto en documentos, discreto en el portal (constitución §11).

## Momento de firma de este encargo
F10: la sección de perfil en la O. Debe verse impecable a 16 px y a 160 px, impresa en una etiqueta de taller y en el favicon de una pestaña. Si a 16 px se pierde el tabique, ajusta la geometría óptica y documenta el ajuste.

## Fuera de alcance
Rediseñar superficies de trabajo (las hacen los demás encargos) y cambiar la API del Orb.

## Criterios de aceptación
- La marca pasa la prueba de tamaño (16, 24, 32, 72, 160 px) en claro y oscuro (capturas en `docs/redesign/captures/marca/`).
- Favicon y manifest correctos en el build de producción (test).
- Login, onboarding, 404/500 y los 5 correos con capturas a 1440 y 390, rúbrica R1–R20 en PASA.
- Test de white-label: un correo y un DOC-01 al cliente no contienen la palabra “DEKOPEN” ni su marca cuando el pie está oculto.
- Test de contraste del color de marca de la organización con fallback a teal-800.
- `docs/design/marca.md` commiteado con construcción y usos prohibidos.
