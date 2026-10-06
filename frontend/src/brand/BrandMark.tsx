/** BrandMark — «La sección»: la cara cortada de un perfil extruido.
 *
 * Geometría sobre retícula 24 (docs/design/marca.md):
 *   exterior 24×24, esquinas r-1 (2 unidades), alma 2.5,
 *   alma interior (web) de 2 a 1/3 del ancho — asimétrico a propósito:
 *   simétrico se lee como ícono de grilla.
 *
 * La tinta es `currentColor`: el mismo trazo sirve en papel (g-950),
 * en oscuro (g-25) y sobre teal-800 (paper). Nunca degradado, contorno
 * ni efecto — la marca es una pieza, no una ilustración.
 */
const SECTION_PATH =
  "M2 0h20a2 2 0 0 1 2 2v20a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2Z" +
  "M2.5 2.5H8V21.5H2.5Z" +
  "M10 2.5h11.5v19H10Z";

export function BrandMark({
  size = 24,
  title,
}: {
  /** Lado del cuadrado en px — mínimo 16 (docs/design/marca.md). */
  size?: number;
  /** Texto accesible; omitir cuando la marca decora junto al wordmark. */
  title?: string;
}): JSX.Element {
  return (
    <svg
      aria-hidden={title === undefined}
      aria-label={title}
      className="brand-mark"
      fill="currentColor"
      fillRule="evenodd"
      height={size}
      role={title === undefined ? undefined : "img"}
      viewBox="0 0 24 24"
      width={size}
    >
      {title === undefined ? null : <title>{title}</title>}
      <path d={SECTION_PATH} />
    </svg>
  );
}
