# Marca DEKOPEN — construcción y uso

La marca se extrae del producto, no se le aplica encima: el isotipo es
**la cara cortada de un perfil extruido** — lo que DEKOPEN fabrica.
Constitución §7, firma F10. Este documento es la norma; cualquier uso
nuevo se verifica contra ella.

## 1. Isotipo — «La sección» (Dirección B)

Retícula de 24 unidades. Fuente canónica:
`frontend/public/favicon.svg` y `frontend/src/brand/BrandMark.tsx`
(un solo path `fill-rule="evenodd"`, idéntico en ambos).

| Elemento | Medida |
|---|---|
| Exterior | 24 × 24, esquinas `r-1` (2 unidades) |
| Alma (muro) | 2.5 |
| Alma interior (web) | 2, ubicada a 1/3 del ancho (x = 8) |
| Cámara izquierda | 5.5 (x: 2.5 → 8) |
| Cámara derecha | 11.5 (x: 10 → 21.5) |

La cámara es la contraforma — el vano que el perfil existe para servir.
El web va a **1/3** y no al centro a propósito: centrado se lee como
ícono de grilla; asimétrico se lee como sección real de catálogo.

**Ajuste óptico documentado:** las esquinas exteriores usan `r-1`
(2/24 ≈ 8 %) para que a 16px la marca no lea «chip» sino perfil.
Las cámaras interiores quedan a escuadra (radio 0): el corte de una
extrusión es recto por dentro.

### Tinta

El trazo es monocromo, siempre `currentColor`:

- papel / superficies claras → `g-950` `#161C1F`
- superficies oscuras → `g-25` `#FCFDFC`
- sobre `teal-800` (ícono de app) → `paper` `#FFFFFF`

El favicon SVG lleva `@media (prefers-color-scheme: dark)` para
conmutar g-950 ↔ g-25; los PNG (favicon, touch, maskable) usan la
versión sobre loseta teal-800, legible en cualquier tema de pestaña.

### Tamaños mínimos

- **Isotipo:** 16 px. A 16px el alma mide 1.67px y las cámaras siguen
  leyendo; verificado en `docs/redesign/captures/marca/` a
  16 / 24 / 32 / 72 / 160 en ambos temas.
- **Wordmark:** 72 px de ancho total (≈ cuerpo de 13px).

### Zona de protección

Media alma (1.25/24 ≈ 5 % del lado) alrededor de la marca: nada entra
ahí — ni texto, ni otros íconos, ni el borde del contenedor. En el
ícono de aplicación la loseta deja 4/24 (16.7 %) de margen, holgado
sobre la zona segura maskable.

### Usos prohibidos

- Degradado, contorno (outline), sombra, bisel o cualquier efecto —
  la marca es una pieza, no una ilustración.
- Deformar (escala no uniforme), rotar salvo en la cama de corte
  documental, cambiar la posición del web ni la proporción de cámaras.
- Tintas fuera de las tres listadas — **nunca** naranja: el naranja es
  la firma («necesita persona»), no el cuerpo de la marca.
- Como patrón repetido, watermark de fondo ni textura.
- Redibujarlo: siempre desde el path canónico.

## 2. Wordmark — `DEK`⧈`PEN`

Plex Sans SemiBold, mayúsculas, tracking `+0.06em`, `g-950`
(`g-25` en oscuro). La sección ocupa el lugar de la **O** — el
producto es la letra. Componente: `frontend/src/brand/Wordmark.tsx`.

- La marca se dimensiona a `0.73em` (cap-height de Plex Sans ≈ 0.714
  + overshoot óptico) y baja a la línea base con `-0.02em` de
  compensación — la O real sobresale de la cap-height igual.
- Interletraje alrededor de la marca: `0.06em`, igual que entre letras
  — la O deja de ser letra, no deja de ser palabra.
- Nunca en minúsculas, nunca con otra tipografía, nunca separado en
  «DEK OPEN». La marca solo reemplaza la O dentro del wordmark
  completo; no se usa la marca como letra en otros textos.

## 3. DocLockup — «La cota» (Dirección D)

Lockup secundario: el wordmark enmarcado por una línea de cota.
Componente: `frontend/src/brand/DocLockup.tsx`.

- Líneas de extensión en los bordes D/N, sobrepasan la línea base
  hasta la línea de cota (12px bajo el wordmark en la implementación).
- Línea de cota `0.75` de peso, ticks oblicuos a `45°` × 3 de largo
  en los puntos de medida.
- Medida en Plex Mono `10.5`, `g-500`/`text-tertiary`, centrada.
- Medida declarada por defecto: **`2 400`** — el ancho canónico del
  vano demo del producto (`2 400 × 1 800`), no un número decorativo.

**Dónde vive:** portada interna de documentos del sistema (cuando
aplique), «Acerca de» y correos transaccionales internos. Nunca como
favicon, nunca como ícono, nunca en el rail — el rail lleva el
wordmark simple.

## 4. Aplicación por punto de contacto

| Superficie | Marca |
|---|---|
| Rail de la app | `Wordmark` 13px en el encabezado |
| Login / magic-link / onboarding | `DocLockup` + hoja técnica |
| Favicon / íconos | Sección sola (SVG adaptativo + PNG loseta teal-800) |
| Correos internos | Sección + `DEKOPEN` en cabecera |
| Correos al cliente | **Sin marca DEKOPEN** — white-label de la org |
| Documentos emitidos (DOC-01…) | **Sin marca DEKOPEN** salvo pie «Generado con DEKOPEN», oculto por defecto (`doc_dekopen_credit`) |
| Portal del cliente | «Generado con DEKOPEN» discreto en el pie |

## 5. Relación con el Orb

El Orb es el asistente («Asistente DEKOPEN»), no la marca: grafito
esférico, órbita teal, ojos de señal. Comparte paleta (grafito + teal)
y nada más — no se usa como ícono de la app ni como parte del lockup.
La sección y el Orb nunca aparecen fundidos en un solo símbolo.
