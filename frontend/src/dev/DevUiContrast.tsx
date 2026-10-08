/** /dev/ui/mal — la misma pantalla dos veces: «Mal» reproduce el tablero
 * board-06 (premium SaaS genérico) y «Bien» lo resuelve con el sistema v2.
 *
 * Este archivo vive en src/dev/ excluido de los guards §10 — la columna «Mal»
 * viola la Constitución A PROPÓSITO: gradientes, radios grandes, morado IA,
 * emoji, exclamaciones e inglés son exactamente lo que los guards atrapan si
 * alguien los cuela en src/. */
import { Link } from "react-router-dom";

import {
  Area,
  Button,
  DataTable,
  DateOnly,
  EntityCode,
  Icon,
  IconButton,
  Money,
  Percent,
  StatusChip,
  Tabs,
  Timestamp,
  TraceButton,
  type Column,
} from "../ui";
import "./dev-ui.css";

type BadRow = { id: string; code: string; desc: string; area: number; price: number };

const ROWS: BadRow[] = [
  { id: "P-01", code: "COT-P-000042-REV-A", desc: "Corredera 2H PVC", area: 2.16, price: 512300 },
  { id: "P-02", code: "COT-P-000043-REV-A", desc: "Abatible aluminio", area: 1.44, price: 388700 },
  { id: "P-03", code: "COT-P-000044-REV-A", desc: "Fijo termopanel", area: 3.2, price: 615900 },
];

function MalColumn(): JSX.Element {
  return (
    <div className="mal">
      <div className="mal__card">
        <h3 className="mal__title">Awesome Quotation Tool 🚀</h3>
        <p className="mal__sub">Supercharge your window business!!</p>
        <div className="mal__stats">
          <div className="mal__stat">
            <span className="mal__stat-value">$1.516.900</span>
            <span className="mal__stat-label">💰 Revenue</span>
          </div>
          <div className="mal__stat">
            <span className="mal__stat-value">38.4%</span>
            <span className="mal__stat-label">📈 Growth</span>
          </div>
          <div className="mal__stat">
            <span className="mal__stat-value">12</span>
            <span className="mal__stat-label">✨ Projects</span>
          </div>
        </div>
        <div className="mal__actions">
          <button className="mal__btn mal__btn--cta">Submit ✨</button>
          <button className="mal__btn mal__btn--cta">Save Draft 💾</button>
          <button className="mal__btn mal__btn--cta">Publish 🎉</button>
        </div>
        <p className="mal__err">Something went wrong! Please try again later!</p>
        <div className="mal__list">
          {ROWS.map((r) => (
            <div className="mal__item" key={r.id}>
              <span className="mal__item-name">{r.desc}</span>
              <span className="mal__item-meta">QUOTED · status: QUOTED</span>
              <span className="mal__item-price">${r.price.toFixed(4)}</span>
              <button className="mal__chip mal__chip--green">ACCEPTED</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function BienColumn(): JSX.Element {
  const columns: Column<BadRow>[] = [
    { key: "pos", label: "Pos.", render: (r) => r.id, width: "3.5rem" },
    { key: "code", label: "Código", render: (r) => <EntityCode value={r.code} /> },
    { key: "desc", label: "Tipología", render: (r) => r.desc },
    {
      key: "area",
      label: "Área",
      numeric: true,
      render: (r) => <Area value={r.area} />,
    },
    {
      key: "price",
      label: "Precio",
      numeric: true,
      render: (r) => (
        <span className="dev-trace-inline">
          <Money value={r.price} />
          <TraceButton
            trace={{
              formula: "ancho × alto × precio_m²",
              authority: "Lista de precios v4",
              engineVersion: "engine 0.9.1",
            }}
          />
        </span>
      ),
    },
    {
      key: "estado",
      label: "Estado",
      render: () => <StatusChip enumName="ProjectResponseStatusEnum" value="QUOTED" />,
    },
  ];
  return (
    <div className="bien">
      <header className="bien__head" data-region="bien-header">
        <div>
          <p className="bien__kicker">Cotización · REV-A</p>
          <h3 className="bien__title">COT-P-000042</h3>
        </div>
        <div className="bien__actions">
          <IconButton icon={<Icon name="print" />} label="Imprimir" />
          <Button size="compact" variant="ghost">
            Historial
          </Button>
          <Button size="compact" variant="primary">
            Emitir revisión
          </Button>
        </div>
      </header>
      <Tabs
        items={[
          { id: "pos", label: "Posiciones (3)" },
          { id: "doc", label: "Documento" },
          { id: "hist", label: "Historial" },
        ]}
        label="Secciones"
        onChange={() => {}}
        value="pos"
      />
      <DataTable
        ariaLabel="Posiciones de la cotización"
        columns={columns}
        rows={ROWS}
        rowKey={(r) => r.id}
      />
      <div className="bien__foot">
        <dl className="bien__totals">
          <div>
            <dt>Total</dt>
            <dd>
              <Money value={1516900} />
            </dd>
          </div>
          <div>
            <dt>Margen</dt>
            <dd>
              <Percent kind="fraction" value={0.325} />
            </dd>
          </div>
          <div>
            <dt>Emitida</dt>
            <dd>
              <Timestamp value="2026-10-01T14:32:00-03:00" />
            </dd>
          </div>
          <div>
            <dt>Entrega</dt>
            <dd>
              <DateOnly value="2026-10-18" />
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

export function DevUiContrast(): JSX.Element {
  return (
    <div className="dev-contrast">
      <header className="dev-contrast__head">
        <div>
          <p className="dev-contrast__kicker">board-06</p>
          <h1>Mismo trabajo, dos idiomas</h1>
          <p>
            A la izquierda, el patrón «premium SaaS» que la Constitución prohíbe; a la derecha, la
            misma superficie con el sistema v2.
          </p>
        </div>
        <Link className="ui-button ui-button--ghost" to="/dev/ui">
          ← Muestrario
        </Link>
      </header>
      <div className="dev-contrast__cols">
        <section aria-label="Mal" className="dev-contrast__col dev-contrast__col--mal">
          <h2>
            <span aria-hidden>✗</span> Mal — SaaS genérico
          </h2>
          <ul className="dev-contrast__notes">
            <li>Degradado + morado IA en lugar del teal del perfil técnico.</li>
            <li>Radios 16 px, sombras difusas, tarjetas «glass».</li>
            <li>Tres CTA primarios: ninguna jerarquía.</li>
            <li>Emoji, exclamaciones, inglés, MAYÚSCULAS en chips.</li>
            <li>Error «Something went wrong!» sin qué pasó ni qué hacer.</li>
          </ul>
          <MalColumn />
        </section>
        <section aria-label="Bien" className="dev-contrast__col">
          <h2>
            <span aria-hidden>✓</span> Bien — sistema v2
          </h2>
          <ul className="dev-contrast__notes">
            <li>Una acción primaria por región; el resto ghost/compacto.</li>
            <li>Números en Mono a la derecha, unidades silenciadas.</li>
            <li>Estado = chip con etiqueta + tono + icono, nunca solo color.</li>
            <li>Cada cifra derivable responde «¿de dónde sale?».</li>
            <li>Sin degradados, sin blur, radios ≤ 4 px, voz de taller.</li>
          </ul>
          <BienColumn />
        </section>
      </div>
    </div>
  );
}
