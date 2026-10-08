import { Wordmark } from "./Wordmark";

/** DocLockup — Dirección D «La cota»: el wordmark enmarcado por una línea
 * de cota. Líneas de extensión que sobrepasan la línea base 2, línea de
 * cota de 0.75 con ticks oblicuos a 45° de 3 de largo, y la medida en
 * Plex Mono debajo. Solo para portada interna, «Acerca de» y correos —
 * nunca como ícono ni favicon (docs/design/marca.md).
 *
 * La medida declarada es 2 400: el ancho canónico del vano demo del
 * producto (2 400 × 1 800), no un número decorativo.
 */
export function DocLockup({
  size = 20,
  measure = "2 400",
  className,
}: {
  /** Cuerpo del wordmark en px. */
  size?: number;
  /** Texto de la cota en mm, sin unidad. */
  measure?: string;
  className?: string;
}): JSX.Element {
  return (
    <span
      className={className === undefined ? "brand-doclockup" : `brand-doclockup ${className}`}
      style={{ fontSize: size }}
    >
      <span className="brand-doclockup__word">
        <Wordmark size={size} />
      </span>
      <span aria-hidden="true" className="brand-doclockup__dimline">
        <svg className="brand-doclockup__tick" viewBox="0 0 6 6">
          <path d="M1 5 5 1" />
        </svg>
        <span className="brand-doclockup__rule" />
        <svg className="brand-doclockup__tick" viewBox="0 0 6 6">
          <path d="M1 5 5 1" />
        </svg>
      </span>
      <span className="brand-doclockup__measure">{measure}</span>
    </span>
  );
}
