import { BrandMark } from "./BrandMark";

/** Wordmark — `DEK`⧈`PEN`: la sección ocupa el lugar de la O.
 * Plex Sans SemiBold, mayúsculas, tracking +0.06em, g-950 (g-25 en
 * oscuro). La marca se dimensiona a la altura de la O (~0.73em:
 * cap-height 0.714 + overshoot óptico) y se apoya en la línea base.
 * Mínimo 72px de ancho total ≈ size 13 (docs/design/marca.md).
 */
export function Wordmark({
  size = 13,
  className,
}: {
  /** Cuerpo tipográfico en px. */
  size?: number;
  className?: string;
}): JSX.Element {
  const markSize = Math.round(size * 0.73 * 2) / 2;
  return (
    <span
      className={className === undefined ? "brand-wordmark" : `brand-wordmark ${className}`}
      style={{ fontSize: size }}
    >
      DEK
      <BrandMark size={markSize} />
      PEN
    </span>
  );
}
