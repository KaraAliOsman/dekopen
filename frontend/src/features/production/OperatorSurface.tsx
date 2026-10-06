/** P12 — la vista del operario: una tablet, guantes, 1024×768, oscuro por
 * defecto y botones de 44 px mínimo. El operario ve SOLO la cola de su
 * estación: qué hacer ahora, la lista de piezas, y tres acciones —
 * Completar, Bloquear (motivo predefinido) y Nota. Sin precios, sin
 * clientes, sin margen: datos comerciales no entran a esta superficie.
 *
 * Escaneo: la etiqueta es la entrada principal. Un código P01-U02-M03 (o
 * la etiqueta QR del bulto) abre la OT en el paso de esa estación; con la
 * pieza enfocada la pantalla entera la muestra (F9 — una pieza, una
 * pantalla, código en Mono ≥32 px). */

import { useEffect, useMemo, useRef, useState } from "react";

import type {
  ProductionOrder,
  ProductionOrderDetail,
  ProductionOrderTrace,
  ProductionStep,
} from "../../api/generated/models";
import { fmtMm, formatDate } from "../../format";
import { t } from "../../i18n/es-CL";
import { Dialog } from "../../ui";
import { stationCodeLabel } from "./labels";
import { OperatorStepCard, type QcCheckInput } from "./OperatorCard";
import { buildPieceList, parsePieceCode } from "./pieces";
import type { StationQueueEntry, StationQueueGroup } from "./queue";

type StepAction = "START" | "COMPLETE" | "BLOCK" | "UNBLOCK" | "NOTE" | "QC_FAIL";

const STATION_STORAGE_PREFIX = "dekopen.operatorStation.";

/** Motivos predefinidos — el operario elige con un toque, no escribe. */
const BLOCK_REASONS = [
  "production.blockReasonMaterial",
  "production.blockReasonTool",
  "production.blockReasonDamaged",
  "production.blockReasonMeasure",
  "production.blockReasonMachine",
] as const;

type Props = {
  userId: string;
  queue: StationQueueGroup[];
  orders: ProductionOrder[];
  /** OT abierta (cuando el operario abrió una entrada o escaneó). */
  detail: ProductionOrderDetail | null;
  trace: ProductionOrderTrace | null;
  detailBusy: boolean;
  traceBusy: boolean;
  /** Pieza escaneada enfocada (código impreso) — dispara la vista F9. */
  focusPiece: string | null;
  onClearFocus: () => void;
  onSelectOrder: (orderId: string | null, stepCode?: string | null) => void;
  onScan: (code: string) => void;
  onStepAction: (step: ProductionStep, action: StepAction, reason?: string | null) => void;
  onQcCheck: (stepId: string, check: QcCheckInput) => void;
  opsDone: Record<string, string[]>;
  onOpsDoneChange: (stepId: string, ops: string[]) => void;
  busyAction: boolean;
  scanBusy: boolean;
};

function stationStorageKey(userId: string): string {
  return `${STATION_STORAGE_PREFIX}${userId}`;
}

export function readOperatorStation(userId: string): string | null {
  try {
    return window.localStorage.getItem(stationStorageKey(userId));
  } catch {
    return null;
  }
}

function writeOperatorStation(userId: string, code: string): void {
  try {
    window.localStorage.setItem(stationStorageKey(userId), code);
  } catch {
    /* Storage negado: la estación se pide de nuevo al recargar. */
  }
}

export function OperatorSurface(props: Props): JSX.Element {
  const { queue, userId } = props;
  const groups = queue;
  const [station, setStation] = useState<string | null>(() => readOperatorStation(userId));
  const [scan, setScan] = useState("");
  const [blockOpen, setBlockOpen] = useState(false);
  const [blockNote, setBlockNote] = useState("");
  const scanRef = useRef<HTMLInputElement>(null);
  const knownCodes = new Set(groups.map((group) => String(group.code ?? "")));
  const currentStation = station && knownCodes.has(station) ? station : null;
  const myGroup = groups.find((group) => String(group.code) === currentStation);

  useEffect(() => {
    scanRef.current?.focus();
  }, [props.detail, props.focusPiece]);

  function pickStation(code: string): void {
    setStation(code);
    writeOperatorStation(userId, code);
  }

  function submitScan(): void {
    const text = scan.trim();
    if (!text) return;
    setScan("");
    props.onScan(text);
  }

  // ── Vista F9: la etiqueta manda — una pieza, una pantalla. ──────────────
  const focusView =
    props.focusPiece && props.detail ? (
      <FocusedPiece
        code={props.focusPiece}
        detail={props.detail}
        onBack={props.onClearFocus}
        trace={props.trace}
      />
    ) : null;
  if (focusView) {
    return (
      <div className="operator-root" data-density="workshop" data-theme-scope="dark">
        <OperatorTopbar
          onScan={submitScan}
          onScanChange={setScan}
          scan={scan}
          scanBusy={props.scanBusy}
          scanRef={scanRef}
          station={currentStation}
        />
        {focusView}
      </div>
    );
  }

  // ── Sin estación elegida: la pantalla pide la estación una vez. ─────────
  if (!currentStation) {
    return (
      <div className="operator-root" data-density="workshop" data-theme-scope="dark">
        <section className="operator-station-pick">
          <h2>{t("production.operatorPickStation")}</h2>
          <p>{t("production.operatorPickStationHint")}</p>
          <div className="operator-station-pick__grid">
            {groups.length ? (
              groups.map((group) => (
                <button
                  data-station={String(group.code)}
                  key={String(group.code)}
                  onClick={() => pickStation(String(group.code))}
                  type="button"
                >
                  <strong>{stationCodeLabel(String(group.code ?? ""))}</strong>
                  <span>
                    {t("production.stationQueueCounts")
                      .replace("{ready}", String(group.pending ?? 0))
                      .replace("{active}", String(group.in_progress ?? 0))
                      .replace("{blocked}", String(group.blocked ?? 0))}
                  </span>
                </button>
              ))
            ) : (
              <p className="production-trace-empty">{t("production.operatorNoStations")}</p>
            )}
          </div>
        </section>
      </div>
    );
  }

  // ── OT abierta: el paso de mi estación, grande. ─────────────────────────
  if (props.detail) {
    const detail = props.detail;
    const mySteps = (detail.steps ?? []).filter((step) => String(step.code) === currentStation);
    const step =
      mySteps.find((entry) => entry.status !== "DONE") ?? mySteps[mySteps.length - 1] ?? null;
    const entry = (myGroup?.entries ?? []).find((item) => item.order_id === detail.id);
    return (
      <div className="operator-root" data-density="workshop" data-theme-scope="dark">
        <OperatorTopbar
          onScan={submitScan}
          onScanChange={setScan}
          scan={scan}
          scanBusy={props.scanBusy}
          scanRef={scanRef}
          station={currentStation}
        />
        <header className="operator-order-head">
          <button
            aria-label={t("production.operatorBackToQueue")}
            className="operator-back"
            onClick={() => props.onSelectOrder(null)}
            type="button"
          >
            ← {t("production.operatorBackToQueue")}
          </button>
          <div className="operator-order-head__id">
            <strong className="operator-order-code">{detail.order_code}</strong>
            <span className="operator-order-head__station">
              · {stationCodeLabel(currentStation)}
            </span>
          </div>
          <div className="operator-order-head__meta">
            {detail.quantity != null ? (
              <span>
                {detail.quantity}{" "}
                {detail.quantity === 1 ? t("production.unitsOne") : t("production.units")}
              </span>
            ) : null}
            {detail.committed_date ? (
              <time dateTime={detail.committed_date}>{formatDate(detail.committed_date)}</time>
            ) : null}
          </div>
        </header>
        {step ? (
          <OperatorStepCard
            actionBar={
              <OperatorActions
                busy={props.busyAction}
                onBlock={() => setBlockOpen(true)}
                onNote={(reason) => props.onStepAction(step, "NOTE", reason)}
                onStepAction={(action, reason) => props.onStepAction(step, action, reason)}
                step={step}
              />
            }
            onOpsDoneChange={(ops) => props.onOpsDoneChange(step.id, ops)}
            onQcCheck={props.onQcCheck}
            opsCheckable
            opsDone={props.opsDone[step.id] ?? []}
            step={step}
            trace={props.trace}
            traceBusy={props.traceBusy}
          />
        ) : (
          <p className="production-trace-empty">{t("production.operatorOrderNoStep")}</p>
        )}
        {entry?.note ? <p className="operator-entry-note">{entry.note}</p> : null}
        <BlockDialog
          busy={props.busyAction}
          note={blockNote}
          onClose={() => setBlockOpen(false)}
          onNoteChange={setBlockNote}
          onSubmit={(reason) => {
            if (step) props.onStepAction(step, "BLOCK", reason);
            setBlockOpen(false);
            setBlockNote("");
          }}
          open={blockOpen}
        />
      </div>
    );
  }

  // ── Cola de mi estación: «Siguiente» + el resto. ─────────────────────────
  const entries = (myGroup?.entries ?? []).filter((entry) => entry.status !== "DONE");
  // «Siguiente» = lo que el operario puede hacer AHORA: un paso BLOCKED es
  // el siguiente de su OT pero no es accionable (solo el encargado lo
  // destraba). Los bloqueados siguen visibles en la cola con su motivo.
  const nextEntry =
    entries.find((entry) => entry.is_next && entry.status !== "BLOCKED") ??
    entries.find((entry) => entry.status !== "BLOCKED") ??
    null;
  const rest = entries.filter((entry) => entry !== nextEntry);
  return (
    <div className="operator-root" data-density="workshop" data-theme-scope="dark">
      <OperatorTopbar
        onScan={submitScan}
        onScanChange={setScan}
        scan={scan}
        scanBusy={props.scanBusy}
        scanRef={scanRef}
        station={currentStation}
      />
      <header className="operator-queue-head">
        <h2>{stationCodeLabel(currentStation)}</h2>
        <span className="operator-queue-head__counts">
          {t("production.stationQueueCounts")
            .replace("{ready}", String(myGroup?.pending ?? 0))
            .replace("{active}", String(myGroup?.in_progress ?? 0))
            .replace("{blocked}", String(myGroup?.blocked ?? 0))}
        </span>
        <button onClick={() => setStation(null)} type="button">
          {t("production.operatorChangeStation")}
        </button>
      </header>
      {nextEntry ? (
        <NextCard
          entry={nextEntry}
          onOpen={(orderId) => props.onSelectOrder(orderId, currentStation)}
        />
      ) : (
        <p className="production-trace-empty operator-empty">
          {t("production.operatorQueueEmpty")}
        </p>
      )}
      {rest.length ? (
        <section aria-label={t("production.operatorRestQueue")} className="operator-rest">
          <h3>{t("production.operatorRestQueue")}</h3>
          <ol>
            {rest.map((entry) => (
              <QueueRow
                entry={entry}
                key={entry.step_id ?? entry.order_id}
                onOpen={(orderId) => props.onSelectOrder(orderId, currentStation)}
              />
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}

function OperatorTopbar({
  station,
  scan,
  onScanChange,
  onScan,
  scanBusy,
  scanRef,
}: {
  station: string | null;
  scan: string;
  onScanChange: (value: string) => void;
  onScan: () => void;
  scanBusy: boolean;
  scanRef: React.RefObject<HTMLInputElement>;
}): JSX.Element {
  return (
    <div className="operator-topbar">
      {station ? (
        <span className="operator-topbar__station">{stationCodeLabel(station)}</span>
      ) : (
        <span />
      )}
      <input
        aria-label={t("production.operatorScanLabel")}
        autoComplete="off"
        className="operator-scan"
        disabled={scanBusy}
        onChange={(event) => onScanChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") onScan();
        }}
        placeholder={t("production.operatorScanPlaceholder")}
        ref={scanRef}
        value={scan}
      />
      <button disabled={scanBusy || !scan.trim()} onClick={onScan} type="button">
        {t("production.operatorScanGo")}
      </button>
    </div>
  );
}

function NextCard({
  entry,
  onOpen,
}: {
  entry: StationQueueEntry;
  onOpen: (orderId: string) => void;
}): JSX.Element {
  return (
    <section aria-label={t("production.operatorNextTitle")} className="operator-next">
      <h3>{t("production.operatorNextTitle")}</h3>
      <button
        className="operator-next__card"
        onClick={() => entry.order_id && onOpen(entry.order_id)}
        type="button"
      >
        <span className="operator-next__order">{entry.order_code}</span>
        <span className="operator-next__step">{entry.label ?? ""}</span>
        <span className="operator-next__cta">{t("production.operatorOpen")}</span>
      </button>
    </section>
  );
}

function QueueRow({
  entry,
  onOpen,
}: {
  entry: StationQueueEntry;
  onOpen: (orderId: string) => void;
}): JSX.Element {
  return (
    <li>
      <button
        className="operator-queue-row"
        onClick={() => entry.order_id && onOpen(entry.order_id)}
        type="button"
      >
        <span className="operator-queue-row__order">{entry.order_code}</span>
        <span className="operator-queue-row__step">{entry.label ?? ""}</span>
        {entry.status === "BLOCKED" ? (
          <span className="operator-queue-row__blocked">{t("production.stepBlocked")}</span>
        ) : null}
      </button>
    </li>
  );
}

/** Acciones del paso — ≥44 px, tres botones, nada más. QC lo firma el
 * encargado: en el paso QC el operario registra medidas, no cierra. */
function OperatorActions({
  step,
  busy,
  onStepAction,
  onBlock,
  onNote,
}: {
  step: ProductionStep;
  busy: boolean;
  onStepAction: (action: StepAction, reason?: string | null) => void;
  onBlock: () => void;
  onNote: (reason: string | null) => void;
}): JSX.Element {
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteText, setNoteText] = useState("");
  const isQc = String(step.code) === "QC";
  const canStart = step.status === "READY" || step.status === "PENDING";
  const inProgress = step.status === "IN_PROGRESS";
  return (
    <div className="operator-actions">
      {canStart ? (
        <button
          className="operator-btn operator-btn--primary"
          disabled={busy}
          onClick={() => onStepAction("START")}
          type="button"
        >
          {t("production.operatorStart")}
        </button>
      ) : null}
      {inProgress && !isQc ? (
        <button
          className="operator-btn operator-btn--primary"
          disabled={busy}
          onClick={() => onStepAction("COMPLETE")}
          type="button"
        >
          {t("production.operatorComplete")}
        </button>
      ) : null}
      {inProgress && isQc ? (
        <p className="operator-qc-hint">{t("production.operatorQcHint")}</p>
      ) : null}
      {step.status !== "DONE" && step.status !== "BLOCKED" ? (
        <>
          <button
            className="operator-btn operator-btn--warn"
            disabled={busy}
            onClick={onBlock}
            type="button"
          >
            {t("production.operatorBlock")}
          </button>
          <button
            className="operator-btn"
            disabled={busy}
            onClick={() => setNoteOpen(true)}
            type="button"
          >
            {t("production.operatorNote")}
          </button>
        </>
      ) : null}
      {step.status === "BLOCKED" ? (
        <p className="operator-blocked-hint">
          {t("production.operatorBlockedHint")}
          {step.note ? ` · ${step.note}` : ""}
        </p>
      ) : null}
      {noteOpen ? (
        <Dialog
          footer={
            <>
              <button onClick={() => setNoteOpen(false)} type="button">
                {t("ui.cancel")}
              </button>
              <button
                className="is-primary"
                disabled={!noteText.trim()}
                onClick={() => {
                  onNote(noteText.trim());
                  setNoteText("");
                  setNoteOpen(false);
                }}
                type="button"
              >
                {t("production.operatorNoteSave")}
              </button>
            </>
          }
          onClose={() => setNoteOpen(false)}
          title={t("production.noteReasonTitle")}
        >
          <label className="operator-note-field">
            {t("production.noteLabel")}
            <textarea
              onChange={(event) => setNoteText(event.target.value)}
              rows={3}
              value={noteText}
            />
          </label>
        </Dialog>
      ) : null}
    </div>
  );
}

/** Bloqueo con motivos predefinidos — un toque, sin teclado, «Otro» abre
 * el campo libre. El motivo viaja como nota del bloqueo: es la instrucción
 * para quien desbloquea. */
function BlockDialog({
  open,
  onClose,
  onSubmit,
  busy,
  note,
  onNoteChange,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (reason: string) => void;
  busy: boolean;
  note: string;
  onNoteChange: (value: string) => void;
}): JSX.Element {
  const [other, setOther] = useState(false);
  useEffect(() => {
    if (open) {
      setOther(false);
      onNoteChange("");
    }
    // onNoteChange es estable en la práctica; solo importa `open`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  if (!open) return <></>;
  return (
    <Dialog onClose={onClose} title={t("production.blockReasonTitle")}>
      <div className="operator-block-reasons">
        {BLOCK_REASONS.map((key) => (
          <button disabled={busy} key={key} onClick={() => onSubmit(t(key))} type="button">
            {t(key)}
          </button>
        ))}
        <button disabled={busy} onClick={() => setOther(true)} type="button">
          {t("production.blockReasonOther")}
        </button>
      </div>
      {other ? (
        <label className="operator-note-field">
          {t("production.blockReasonOtherLabel")}
          <input onChange={(event) => onNoteChange(event.target.value)} value={note} />
          <button
            className="operator-btn operator-btn--warn"
            disabled={busy || !note.trim()}
            onClick={() => onSubmit(note.trim())}
            type="button"
          >
            {t("production.operatorBlock")}
          </button>
        </label>
      ) : null}
    </Dialog>
  );
}

/** F9 — la pieza ocupa toda la pantalla: código en Mono enorme, medidas,
 * en qué estación trabaja y qué sigue después. */
function FocusedPiece({
  code,
  detail,
  trace,
  onBack,
}: {
  code: string;
  detail: ProductionOrderDetail;
  trace: ProductionOrderTrace | null;
  onBack: () => void;
}): JSX.Element {
  const pieces = useMemo(() => buildPieceList(trace), [trace]);
  const normalized = code.trim().toUpperCase();
  const piece = pieces.find((item) => item.code.toUpperCase() === normalized);
  const parsed = parsePieceCode(normalized);
  const openSteps = (detail.steps ?? []).filter((step) => step.status !== "DONE");
  const nextStep = openSteps[0] ?? null;
  const following = openSteps.slice(1, 4);
  return (
    <section aria-label={code} className="operator-focus">
      <button className="operator-back" onClick={onBack} type="button">
        ← {t("production.operatorBackToQueue")}
      </button>
      <p className="operator-focus__label">{t("production.operatorPieceLabel")}</p>
      <strong className="operator-focus__code">{code}</strong>
      <dl className="operator-focus__meta">
        <div>
          <dt>{t("production.operatorPieceOrder")}</dt>
          <dd>{detail.order_code}</dd>
        </div>
        {piece?.lengthMm != null ? (
          <div>
            <dt>{t("production.traceLength")}</dt>
            <dd>{fmtMm(piece.lengthMm)} mm</dd>
          </div>
        ) : null}
        {piece?.widthMm != null && piece.heightMm != null ? (
          <div>
            <dt>{t("production.optimizeSize")}</dt>
            <dd>
              {fmtMm(piece.widthMm)} × {fmtMm(piece.heightMm)}
            </dd>
          </div>
        ) : null}
        {piece?.sku ? (
          <div>
            <dt>{t("production.optimizeSku")}</dt>
            <dd>{piece.sku}</dd>
          </div>
        ) : null}
        {parsed.unitIndex != null ? (
          <div>
            <dt>{t("production.operatorPieceUnit")}</dt>
            <dd>U{String(parsed.unitIndex).padStart(2, "0")}</dd>
          </div>
        ) : null}
      </dl>
      <div className="operator-focus__next">
        {nextStep ? (
          <>
            <p>{t("production.operatorPieceNow")}</p>
            <strong>{nextStep.label ?? stationCodeLabel(String(nextStep.code ?? ""))}</strong>
            {following.length ? (
              <p className="operator-focus__then">
                {t("production.operatorPieceThen")}{" "}
                {following
                  .map((step) => step.label ?? stationCodeLabel(String(step.code ?? "")))
                  .join(" → ")}
              </p>
            ) : null}
          </>
        ) : (
          <p>{t("production.operatorPieceDone")}</p>
        )}
      </div>
    </section>
  );
}
