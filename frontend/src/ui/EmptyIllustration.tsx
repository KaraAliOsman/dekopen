/** EmptyIllustration — láminas técnicas para estados vacíos (P25).
 *
 * En vez de ilustraciones genéricas, cada estado vacío dibuja lo que falta
 * con la gramática del producto: una elevación vacía con cotas fantasma
 * («sin posiciones»), una barra sin cortes («sin plan de corte»), una hoja
 * con rótulo («sin documentos»), un banco de corte («sin órdenes») y una
 * mesa de proyecto («sin clientes»). Trazo fino 1.5 sobre retícula 120×80,
 * tinta currentColor atenuada por el contenedor — nunca rellenos alegres.
 */

export type EmptyIllustrationKind = "elevation" | "bar" | "document" | "order" | "bench";

const W = 120;
const H = 80;

/** Marca de cota a 45° — el mismo tick del bloqueo DocLockup. */
function Tick({ x, y }: { x: number; y: number }): JSX.Element {
  return <path d={`M${x - 2.5} ${y + 2.5}L${x + 2.5} ${y - 2.5}`} />;
}

function Elevation(): JSX.Element {
  // Van vacío: el marco dibujado a ras, la hoja interior en fantasma
  // discontinuo y la cota de ancho con ticks — el dato que falta es la medida.
  return (
    <>
      <rect x="34" y="10" width="52" height="52" rx="1.5" />
      <rect className="is-ghost" x="38" y="14" width="20" height="44" rx="1" />
      <rect className="is-ghost" x="62" y="14" width="20" height="44" rx="1" />
      <path className="is-ghost" d="M60 14v44" />
      <path d="M34 70h52" className="is-dim" />
      <path d="M34 66v8M86 66v8" className="is-dim" />
      <Tick x={40} y={68.5} />
      <Tick x={80} y={68.5} />
      <text x="60" y="77" className="empty-ill__dim" fontSize={6}>
        —
      </text>
    </>
  );
}

function Bar(): JSX.Element {
  // Barra de perfil sin cortes: el perfil a ras, las marcas de corte en
  // fantasma — falta el plan que las active.
  return (
    <>
      <rect x="8" y="30" width="104" height="14" rx="1.5" />
      <path className="is-ghost" d="M8 37h104" />
      {[30, 52, 74, 94].map((x) => (
        <path key={x} className="is-ghost" d={`M${x} 26v26`} />
      ))}
      <path d="M8 58h104" className="is-dim" />
      <path d="M8 54v8M112 54v8" className="is-dim" />
      <Tick x={14} y={56.5} />
      <Tick x={106} y={56.5} />
      <text x="60" y="66" className="empty-ill__dim" fontSize={6}>
        6 500
      </text>
    </>
  );
}

function Document(): JSX.Element {
  // Hoja de taller con rótulo y renglones fantasma — falta el contenido.
  return (
    <>
      <path d="M38 8h34l12 12v52H38Z" />
      <path d="M72 8v12h12" />
      <path className="is-ghost" d="M44 30h28M44 36h28M44 42h20" />
      <path d="M38 60h46" className="is-dim" />
      <path className="is-ghost" d="M44 64h14" />
      <text x="78" y="68" className="empty-ill__dim" fontSize={6}>
        DOC
      </text>
    </>
  );
}

function Order(): JSX.Element {
  // Estación de trabajo: dos láminas apiladas y un cronómetro — falta la OT.
  return (
    <>
      <rect x="18" y="22" width="34" height="44" rx="1.5" />
      <rect className="is-ghost" x="24" y="16" width="34" height="44" rx="1.5" />
      <circle cx="84" cy="38" r="14" />
      <path className="is-ghost" d="M84 30v8l6 4" />
      <path className="is-dim" d="M18 74h84" />
    </>
  );
}

function Bench(): JSX.Element {
  // Banco de trabajo vacío: la mesa a ras y la lámina fantasma — falta el
  // primer cliente/proyecto.
  return (
    <>
      <path d="M10 62h100" />
      <path d="M18 62v8M102 62v8" className="is-dim" />
      <rect className="is-ghost" x="34" y="30" width="52" height="28" rx="1.5" />
      <path className="is-ghost" d="M40 38h20M40 44h28" />
    </>
  );
}

const KINDS: Record<EmptyIllustrationKind, () => JSX.Element> = {
  elevation: Elevation,
  bar: Bar,
  document: Document,
  order: Order,
  bench: Bench,
};

export function EmptyIllustration({
  kind = "bench",
}: {
  kind?: EmptyIllustrationKind;
}): JSX.Element {
  const Draw = KINDS[kind];
  return (
    <svg aria-hidden="true" className="empty-ill" height={H} viewBox={`0 0 ${W} ${H}`} width={W}>
      <Draw />
    </svg>
  );
}
