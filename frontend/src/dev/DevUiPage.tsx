/** /dev/ui — muestrario del sistema de diseño v2.
 *
 * Solo existe en DEV (`visibleDevOnlyRoutePaths` excluye producción). Cada
 * sección muestra una familia de primitivas en sus cinco estados; la barra
 * superior alterna tema y densidad con los mecanismos reales
 * (`data-theme-scope`, `data-density`), de modo que esta página es a la vez
 * el banco de pruebas visual del §9.3 y el manual del §10.
 */
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { domainLabel } from "../i18n/domainLabels";
import {
  AdvancedGroup,
  Area,
  BlockedState,
  Button,
  ButtonGroup,
  Checkbox,
  Combobox,
  CommandPalette,
  DataTable,
  DateOnly,
  DeniedState,
  Dialog,
  Dims,
  DimLoader,
  Drawer,
  EmptyState,
  EntityCode,
  ErrorState,
  Field,
  Icon,
  IconButton,
  Inspector,
  InspectorGroup,
  KeyValue,
  Length,
  LoadingState,
  Menu,
  Money,
  MoneyField,
  NumberField,
  OpeningGlyph,
  Panel,
  Percent,
  Popover,
  Qty,
  Radio,
  SegmentedControl,
  SelectField,
  SheetSurface,
  SpecList,
  Stat,
  StatusChip,
  Stepper,
  Switch,
  Tabs,
  TextInput,
  Timestamp,
  ToastProvider,
  Tooltip,
  TraceButton,
  UnknownValue,
  Uvalue,
  Weight,
  type Column,
  type SelectOption,
  type StepItem,
} from "../ui";
import "./dev-ui.css";

const DENSITIES = [
  { value: "office", label: "Oficina" },
  { value: "document", label: "Documento" },
  { value: "workshop", label: "Taller" },
] as const;

const SHOWCASE_SECTIONS = [
  ["acciones", "Acciones"],
  ["formularios", "Formularios"],
  ["datos", "Datos"],
  ["dominio", "Etiquetas de dominio"],
  ["estados", "Estados"],
  ["superposicion", "Superposición"],
  ["firma", "Firma"],
] as const;

type DensityValue = (typeof DENSITIES)[number]["value"];

function ScopeControls({
  theme,
  density,
  onTheme,
  onDensity,
}: {
  theme: "light" | "dark";
  density: DensityValue;
  onTheme: (theme: "light" | "dark") => void;
  onDensity: (density: DensityValue) => void;
}): JSX.Element {
  return (
    <div className="dev-scope-bar">
      <strong>dev/ui</strong>
      <SegmentedControl
        name="dev-theme"
        onValueChange={onTheme}
        options={[
          { value: "light", label: "Claro" },
          { value: "dark", label: "Oscuro" },
        ]}
        value={theme}
      />
      <SegmentedControl
        name="dev-density"
        onValueChange={(value) => onDensity(value as DensityValue)}
        options={DENSITIES.map((d) => ({ value: d.value, label: d.label }))}
        value={density}
      />
      <Link className="ui-button ui-button--ghost" to="/dev/ui/mal">
        Bien / Mal →
      </Link>
    </div>
  );
}

function ActionsSection(): JSX.Element {
  const [switchOn, setSwitchOn] = useState(true);
  const [checkA, setCheckA] = useState(true);
  const [checkB, setCheckB] = useState(false);
  const [radio, setRadio] = useState("pvc");
  const [segment, setSegment] = useState("oficina");
  return (
    <Panel className="dev-panel" title="Acciones">
      <div className="dev-row">
        <Button variant="primary">Guardar cotización</Button>
        <Button>Aplicar</Button>
        <Button variant="ghost">Ver traza</Button>
        <Button variant="danger">Anular revisión</Button>
      </div>
      <div className="dev-row">
        <Button loading variant="primary">
          Emitiendo…
        </Button>
        <Button disabled disabledReason="Requiere una revisión emitida">
          Anular
        </Button>
        <Button size="compact">Compacto</Button>
        <Button size="touch" variant="primary">
          Táctil ≥44 px
        </Button>
      </div>
      <div className="dev-row">
        <ButtonGroup>
          <Button size="compact">Cortar</Button>
          <Button size="compact">Optimizar</Button>
          <Button size="compact">Exportar</Button>
        </ButtonGroup>
        <IconButton icon={<Icon name="download" />} label="Descargar" />
        <IconButton disabled icon={<Icon name="trash" />} label="Eliminar" />
      </div>
      <div className="dev-row">
        <Switch
          checked={switchOn}
          hint="Recalcular al cambiar"
          label="Optimización automática"
          onCheckedChange={setSwitchOn}
        />
        <Switch checked={false} disabled label="Deshabilitado" onCheckedChange={() => {}} />
      </div>
      <div className="dev-row">
        <Checkbox
          checked={checkA}
          label="Refuerzo galvanizado"
          onChange={(e) => setCheckA(e.target.checked)}
        />
        <Checkbox
          checked={checkB}
          label="Drenaje exterior"
          onChange={(e) => setCheckB(e.target.checked)}
        />
        <Checkbox checked={false} disabled label="Deshabilitado" />
      </div>
      <div className="dev-row">
        <Radio checked={radio === "pvc"} label="PVC" name="mat" onChange={() => setRadio("pvc")} />
        <Radio
          checked={radio === "alu"}
          label="Aluminio"
          name="mat"
          onChange={() => setRadio("alu")}
        />
      </div>
      <div className="dev-row">
        <SegmentedControl
          name="seg-demo"
          onValueChange={setSegment}
          options={[
            { value: "oficina", label: "Oficina" },
            { value: "terreno", label: "Terreno" },
            { value: "taller", label: "Taller" },
          ]}
          value={segment}
        />
      </div>
    </Panel>
  );
}

function FormsSection(): JSX.Element {
  const [num, setNum] = useState("1249.5");
  const [money, setMoney] = useState("1435471");
  const [sel, setSel] = useState("pvc");
  const [combo, setCombo] = useState("");
  const selectOptions: SelectOption[] = [
    { value: "pvc", label: "PVC" },
    { value: "alu", label: "Aluminio" },
    { value: "mixto", label: "Mixto", disabled: true },
  ];
  const comboboxOptions: SelectOption[] = [
    "Corredera 2 hojas",
    "Corredera 3 hojas",
    "Abatible exterior",
    "Proyectante",
    "Oscilobatiente",
    "Fijo",
    "Puerta de entrada",
  ].map((label, i) => ({ value: `opt-${i}`, label }));
  return (
    <Panel className="dev-panel" title="Formularios">
      {/* noValidate: la validación la da el gancho §4 en español. */}
      <form noValidate onSubmit={(e) => e.preventDefault()}>
        <div className="dev-grid">
          <Field label="Ancho" required>
            <NumberField decimals={1} onValueChange={setNum} suffix="mm" value={num} />
          </Field>
          <Field error="El precio no puede ser negativo." label="Precio lista" required>
            <MoneyField invalid onValueChange={setMoney} value={money} />
          </Field>
          <Field help="Material estructural de la hoja." label="Material">
            <SelectField
              onChange={(e) => setSel(e.target.value)}
              options={selectOptions}
              value={sel}
            />
          </Field>
          <Field label="Tipología">
            <Combobox
              onValueChange={setCombo}
              options={comboboxOptions}
              placeholder="Buscar tipología…"
              value={combo}
            />
          </Field>
          <Field label="RUT cliente">
            <TextInput data-pattern="^[0-9]+-?[0-9kK]$" placeholder="12345678-9" required />
          </Field>
          <Field label="Correo">
            <TextInput placeholder="nombre@empresa.cl" required type="email" />
          </Field>
        </div>
        <div className="dev-row">
          <Button type="submit" variant="primary">
            Validar en español
          </Button>
        </div>
      </form>
    </Panel>
  );
}

type SampleRow = {
  id: string;
  code: string;
  desc: string;
  width: number;
  area: number;
  price: number;
};

const TABLE_ROWS: SampleRow[] = Array.from({ length: 24 }, (_, i) => ({
  id: `P${(i + 1).toString().padStart(2, "0")}`,
  code: `COT-P-0000${(42 + i).toString()}-REV-A`,
  desc: ["Corredera 2H PVC", "Abatible aluminio", "Fijo termopanel", "Proyectante 45°"][i % 4]!,
  width: 1200 + i * 150,
  area: 1.2 + i * 0.35,
  price: 384000 + i * 51700,
}));

function DataSection(): JSX.Element {
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState("lista");
  const columns: Column<SampleRow>[] = [
    { key: "pos", label: "Pos.", render: (r) => r.id, width: "3.5rem" },
    {
      key: "code",
      label: "Código",
      render: (r) => <EntityCode value={r.code} />,
      sortValue: (r) => r.code,
      filterText: (r) => r.code,
    },
    {
      key: "desc",
      label: "Tipología",
      render: (r) => r.desc,
      sortValue: (r) => r.desc,
      filterText: (r) => r.desc,
    },
    {
      key: "width",
      label: "Ancho",
      numeric: true,
      render: (r) => <Length value={r.width} />,
      sortValue: (r) => r.width,
    },
    {
      key: "area",
      label: "Área",
      numeric: true,
      render: (r) => <Area value={r.area} />,
      sortValue: (r) => r.area,
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
              inputs: [
                { label: "Precio m²", value: "$ 182.000" },
                { label: "Tabla", value: "PVC estándar 2026" },
              ],
              authority: "Lista de precios v4",
              engineVersion: "engine 0.9.1",
            }}
          />
        </span>
      ),
      sortValue: (r) => r.price,
    },
  ];
  const steps: StepItem[] = [
    { key: "s1", label: "Medición", state: "done" },
    { key: "s2", label: "Diseño", state: "done" },
    { key: "s3", label: "Cotización", state: "current" },
    { key: "s4", label: "Producción", state: "pending" },
    { key: "s5", label: "Despacho", state: "pending" },
  ];
  return (
    <Panel
      actions={
        <Tabs
          items={[
            { id: "lista", label: "Lista" },
            { id: "detalle", label: "Detalle" },
          ]}
          label="Vista"
          onChange={setTab}
          value={tab}
        />
      }
      className="dev-panel"
      title="Datos"
    >
      <Stepper steps={steps} />
      <DataTable
        ariaLabel="Posiciones de muestra"
        bulkActions={<Button size="compact">Enviar a producción</Button>}
        columns={columns}
        emptyBody="La revisión aún no tiene posiciones."
        emptyTitle="Sin posiciones"
        onSelectionChange={setSel}
        rows={TABLE_ROWS}
        rowKey={(r) => r.id}
        selection={sel}
      />
      <div className="dev-grid">
        <SpecList>
          <KeyValue label="Ancho nominal">
            <Length value={2400} />
          </KeyValue>
          <KeyValue label="Dimensiones">
            <Dims height={1500} width={2400} />
          </KeyValue>
          <KeyValue label="Área vidrio">
            <Area value={2.16} />
          </KeyValue>
          <KeyValue label="Peso hoja">
            <Weight value={38.4} />
          </KeyValue>
          <KeyValue label="Uw">
            <Uvalue value={1.4} />
          </KeyValue>
          <KeyValue label="Cantidad">
            <Qty unit="u" value={3} />
          </KeyValue>
          <KeyValue label="Margen">
            <Percent kind="fraction" value={0.325} />
          </KeyValue>
          <KeyValue label="Diferencia">
            <Percent kind="points" value={1.5} />
          </KeyValue>
          <KeyValue label="Emitida">
            <Timestamp value="2026-10-01T14:32:00-03:00" />
          </KeyValue>
          <KeyValue label="Entrega">
            <DateOnly value="2026-10-18" />
          </KeyValue>
          <KeyValue label="Valor nulo">
            <Money value={null} />
          </KeyValue>
        </SpecList>
        <Stat
          decision="docs/decisions/valores-por-defecto.md#muestrario"
          detail="12 proyectos en el período"
          label="Ticket medio"
          value={<Money value={2430000} />}
        />
      </div>
    </Panel>
  );
}

const DOMAIN_CHIPS: [string, string][] = [
  ["ProjectResponseStatusEnum", "QUOTED"],
  ["ProjectResponseStatusEnum", "APPROVED"],
  ["ProductionStepStatusEnum", "IN_PROGRESS"],
  ["InspectorRuleIdEnum", "R01"],
  ["PaymentStatusEnum", "PENDING"],
  ["DeliveryStatusEnum", "ON_ROUTE"],
  ["MembershipRoleEnum", "INSTALLER"],
];

function DomainSection(): JSX.Element {
  return (
    <Panel className="dev-panel" title="Etiquetas de dominio">
      <div className="dev-row">
        {DOMAIN_CHIPS.map(([en, v]) => (
          <StatusChip enumName={en} key={`${en}:${v}`} value={v} />
        ))}
        <StatusChip enumName="ProjectResponseStatusEnum" value="INEXISTENTE" />
      </div>
      <p className="dev-note">
        El chip resuelve etiqueta + tono + icono desde el enum orval; el estado jamás se expresa
        solo con color.
      </p>
      <div className="dev-row">
        <span className="fmt-num">
          domainLabel → {domainLabel("DeliveryStatusEnum", "ON_ROUTE").label}
        </span>
      </div>
    </Panel>
  );
}

function StatesSection(): JSX.Element {
  return (
    <Panel className="dev-panel" title="Estados">
      <div className="dev-grid dev-grid--states">
        <EmptyState
          action={<Button size="compact">Crear posición</Button>}
          body="Agrega la primera posición para empezar a cotizar."
          title="Sin posiciones"
        />
        <ErrorState
          body="La lista de precios no respondió. Los datos ingresados están a salvo."
          onRetry={() => {}}
        />
        <DeniedState reason="Tu rol actual no puede emitir cotizaciones." />
        <BlockedState
          action={<Button size="compact">Ver cotización</Button>}
          body="La producción requiere una cotización aceptada."
          title="Sin cotización aceptada"
        />
        <LoadingState label="Cargando posiciones" shape="table" />
        <div className="dev-loader-cell">
          <DimLoader label="Midiendo" />
          <p className="dev-note">DimLoader aparece tras 1 s — nunca antes.</p>
        </div>
      </div>
      <div className="dev-row">
        <UnknownValue
          action="Ingresar medición"
          cause="La medición en terreno aún no se registró."
          onAction={() => {}}
        />
      </div>
    </Panel>
  );
}

function OverlaySection(): JSX.Element {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [popOpen, setPopOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const popAnchor = useRef<HTMLButtonElement>(null);
  const menuAnchor = useRef<HTMLButtonElement>(null);
  return (
    <Panel className="dev-panel" title="Superposición">
      <div className="dev-row">
        <Button onClick={() => setDialogOpen(true)}>Abrir diálogo</Button>
        <Button onClick={() => setDrawerOpen(true)}>Abrir drawer</Button>
        <Button onClick={() => setPopOpen(true)} ref={popAnchor}>
          Abrir popover
        </Button>
        <Button onClick={() => setMenuOpen(true)} ref={menuAnchor}>
          Abrir menú
        </Button>
        <Button onClick={() => setPaletteOpen(true)}>Paleta (Ctrl+K)</Button>
        <Tooltip label="Recalcula cortes y vidrios" shortcut="Ctrl+O">
          <Button variant="ghost">Optimizar</Button>
        </Tooltip>
      </div>
      {dialogOpen ? (
        <Dialog
          footer={
            <>
              <Button onClick={() => setDialogOpen(false)} variant="ghost">
                Cancelar
              </Button>
              <Button data-primary onClick={() => setDialogOpen(false)} variant="primary">
                Confirmar
              </Button>
            </>
          }
          onClose={() => setDialogOpen(false)}
          title="Emitir revisión"
        >
          <p>
            La revisión emitida queda congelada. Los cambios posteriores crean una revisión nueva.
          </p>
        </Dialog>
      ) : null}
      {drawerOpen ? (
        <Drawer onClose={() => setDrawerOpen(false)} title="Detalle de posición">
          <SpecList>
            <KeyValue label="Código">
              <EntityCode value="P-01" />
            </KeyValue>
            <KeyValue label="Ancho">
              <Length value={1200} />
            </KeyValue>
            <KeyValue label="Alto">
              <Length value={1500} />
            </KeyValue>
          </SpecList>
        </Drawer>
      ) : null}
      {popOpen ? (
        <Popover anchorRef={popAnchor} onClose={() => setPopOpen(false)}>
          <p className="dev-note">Contenido anclado al invocador.</p>
        </Popover>
      ) : null}
      {menuOpen ? (
        <Popover anchorRef={menuAnchor} onClose={() => setMenuOpen(false)}>
          <Menu
            items={[
              { key: "e", label: "Editar posición", shortcut: "E" },
              { key: "d", label: "Duplicar", shortcut: "Ctrl+D" },
              { key: "x", danger: true, label: "Eliminar" },
            ]}
            onClose={() => setMenuOpen(false)}
          />
        </Popover>
      ) : null}
      <CommandPalette onClose={() => setPaletteOpen(false)} open={paletteOpen} />
    </Panel>
  );
}

function SignatureSection(): JSX.Element {
  const glyphTypes = [
    "TURN_LEFT",
    "TURN_RIGHT",
    "TILT_TURN_LEFT",
    "TILT_TURN_RIGHT",
    "AWNING",
    "SLIDING",
    "SLIDING_2L",
    "DOOR",
    "DOOR_ENTRY",
    "FIXED",
  ];
  return (
    <Panel className="dev-panel" title="Firma">
      <div className="dev-grid dev-grid--signature">
        <SheetSurface className="dev-sheet">
          <p className="dev-sheet__kicker">Ficha técnica · REV-A</p>
          <h3 className="dev-sheet__title">Corredera 2 hojas PVC</h3>
          <SpecList>
            <KeyValue label="Dimensiones">
              <Dims height={1500} width={2400} />
            </KeyValue>
            <KeyValue label="Área">
              <Area value={3.6} />
            </KeyValue>
            <KeyValue label="Precio">
              <Money value={1435471} />
            </KeyValue>
          </SpecList>
        </SheetSurface>
        <div>
          <div className="dev-glyph-grid">
            {glyphTypes.map((type) => (
              <figure className="dev-glyph" key={type}>
                <OpeningGlyph size={44} type={type} />
                <figcaption>{type.toLowerCase()}</figcaption>
              </figure>
            ))}
          </div>
          <p className="dev-note">
            Hacia el observador = trazo continuo · alejándose = discontinuo.
          </p>
          <div className="dev-glyph-grid dev-glyph-grid--away">
            {glyphTypes.slice(0, 5).map((type) => (
              <figure className="dev-glyph" key={type}>
                <OpeningGlyph size={44} toward={false} type={type} />
                <figcaption>{type.toLowerCase()} ext.</figcaption>
              </figure>
            ))}
          </div>
        </div>
      </div>
    </Panel>
  );
}

export function DevUiPage(): JSX.Element {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [density, setDensity] = useState<DensityValue>("office");
  return (
    <ToastProvider>
      <div className="dev-ui" data-density={density} data-theme-scope={theme}>
        <ScopeControls density={density} onDensity={setDensity} onTheme={setTheme} theme={theme} />
        <nav aria-label="Secciones del muestrario" className="dev-toc">
          {SHOWCASE_SECTIONS.map(([id, label]) => (
            <a href={`#dev-${id}`} key={id}>
              {label}
            </a>
          ))}
        </nav>
        <header className="dev-head">
          <h1>Sistema de diseño v2 — muestrario</h1>
          <p>
            Tema {theme === "light" ? "claro" : "oscuro"} · densidad{" "}
            {DENSITIES.find((d) => d.value === density)?.label}. Cada primitiva se muestra en sus
            cinco estados reales.
          </p>
        </header>
        <main className="dev-main">
          <Inspector
            collapsed={false}
            title="Inspector"
            footer={
              <Button size="compact" variant="ghost">
                Restablecer
              </Button>
            }
          >
            <InspectorGroup title="Geometría">
              <SpecList>
                <KeyValue label="Ancho">
                  <Length value={1200} />
                </KeyValue>
                <KeyValue label="Alto">
                  <Length value={1500} />
                </KeyValue>
              </SpecList>
            </InspectorGroup>
            <AdvancedGroup>
              <SpecList>
                <KeyValue label="Tolerancia">
                  <Length value={0.05} />
                </KeyValue>
              </SpecList>
            </AdvancedGroup>
          </Inspector>
          <div className="dev-col">
            <section id="dev-acciones">
              <ActionsSection />
            </section>
            <section id="dev-formularios">
              <FormsSection />
            </section>
            <section id="dev-datos">
              <DataSection />
            </section>
            <section id="dev-dominio">
              <DomainSection />
            </section>
            <section id="dev-estados">
              <StatesSection />
            </section>
            <section id="dev-superposicion">
              <OverlaySection />
            </section>
            <section id="dev-firma">
              <SignatureSection />
            </section>
          </div>
        </main>
        <footer className="dev-foot">
          <p>
            Esta página solo existe en desarrollo. El contraste Bien/Mal vive en{" "}
            <Link to="/dev/ui/mal">/dev/ui/mal</Link>.
          </p>
        </footer>
      </div>
    </ToastProvider>
  );
}
