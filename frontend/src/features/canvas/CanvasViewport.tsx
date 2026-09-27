import {
  createContext,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { t } from "../../i18n/es-CL";
import {
  type Box,
  fitTransform,
  IDENTITY,
  panBy,
  SCALE_100,
  shouldRefitView,
  type ViewTransform,
  zoomAt,
} from "./viewport";

/** Canvas viewport: a pannable/zoomable drawing sheet. Content renders in mm
 * coordinates inside a `<g transform>` the viewport owns. Wheel pans,
 * Ctrl/⌘+wheel zooms to the cursor, space or middle-drag pans, Shift+1 fits,
 * Shift+2 zooms to the selection, Shift+0 restores 100%. A floating island
 * bottom-left carries the same controls; the status readout sits bottom-right. */

const PAN_STEP = 60;

/** Current sheet scale in device px per content mm. Interactive children
 * (divider grips, seams) size their hit areas with it so they stay a constant
 * ~12px on screen at any zoom. SCALE_100 outside a viewport. */
export const ViewportScaleContext = createContext<number>(SCALE_100);

export function useViewportScale(): number {
  return useContext(ViewportScaleContext);
}

export function CanvasViewport({
  contentBox,
  selectionBox,
  status,
  contentEpoch = 0,
  children,
}: {
  contentBox: Box;
  selectionBox: Box | null;
  status: string;
  /** Bumped by the caller when the content is REPLACED wholesale (starter
   * pick, another design loaded) — a manual pan/zoom latch must not leave
   * the new product rendered off-viewport. */
  contentEpoch?: number;
  children: ReactNode;
}): JSX.Element {
  const hostRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  // Pre-fit render: content at 100% near the origin — the first real measure
  // immediately replaces this with a fit transform.
  const [view, setView] = useState<ViewTransform>({
    ...IDENTITY,
    scale: SCALE_100,
    tx: 24,
    ty: 24,
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const [panning, setPanning] = useState(false);
  const fittedRef = useRef(false);
  const spaceRef = useRef(false);
  const dragRef = useRef<{ pointerId: number; x: number; y: number } | null>(null);
  // Auto-fit bookkeeping: once the user manually pans/zooms we stop following
  // contentBox changes (the async plan arriving later must not jump the view).
  const userInteractedRef = useRef(false);
  const lastFitBoxRef = useRef<Box | null>(null);
  const lastFitSizeRef = useRef<{ w: number; h: number }>({ w: 0, h: 0 });
  const lastEpochRef = useRef(0);

  const fit = useCallback(() => {
    lastFitBoxRef.current = contentBox;
    lastFitSizeRef.current = { w: size.w, h: size.h };
    setView(fitTransform(contentBox, size.w, size.h));
  }, [contentBox, size.w, size.h]);

  // Measure the container; first non-zero measure fits the sheet.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const measure = () => setSize({ w: host.clientWidth, h: host.clientHeight });
    measure();
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(measure);
      observer.observe(host);
      return () => observer.disconnect();
    }
  }, []);

  // Consumers size interactive hit areas in screen pixels — they read the
  // current px/mm scale here (view.scale = device px per content mm).
  const scaleContext = view.scale;

  useEffect(() => {
    if (size.w <= 0 || size.h <= 0) return;
    if (!fittedRef.current) {
      fittedRef.current = true;
      fit();
      return;
    }
    // A wholesale content replacement breaks the manual-view latch: the new
    // product would render wherever the old pan/zoom left it — potentially
    // fully off-screen ("blank canvas" on a starter pick).
    const epochChanged = contentEpoch !== lastEpochRef.current;
    if (epochChanged) {
      lastEpochRef.current = contentEpoch;
      userInteractedRef.current = false;
    }
    // Sheet grew (e.g. the plan arrived after the first fit) or the container
    // itself resized (the /new page collapses once a starter applies — a stale
    // transform would clip the drawing off the viewport): refit in both cases,
    // only while the user has not taken manual control of the view. Compared
    // by value — contentBox is rebuilt each render.
    const last = lastFitBoxRef.current;
    const boxChanged =
      last === null ||
      last.x !== contentBox.x ||
      last.y !== contentBox.y ||
      last.w !== contentBox.w ||
      last.h !== contentBox.h;
    const resized = lastFitSizeRef.current.w !== size.w || lastFitSizeRef.current.h !== size.h;
    if (
      shouldRefitView({
        contentEpochChanged: epochChanged,
        boxChanged,
        containerResized: resized,
        userInteracted: userInteractedRef.current,
      })
    )
      fit();
  }, [fit, size, contentBox, contentEpoch]);

  // Space held → pan mode. Listen on window so it works wherever focus sits.
  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code === "Space") spaceRef.current = true;
    };
    const up = (event: KeyboardEvent) => {
      if (event.code === "Space") spaceRef.current = false;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  // Native wheel listener: React's delegated wheel events are passive and
  // cannot preventDefault for zoom-to-cursor.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      userInteractedRef.current = true;
      const rect = host.getBoundingClientRect();
      if (event.ctrlKey || event.metaKey) {
        const factor = Math.pow(1.0015, -event.deltaY);
        setView((current) =>
          zoomAt(current, event.clientX - rect.left, event.clientY - rect.top, factor),
        );
      } else if (event.shiftKey) {
        setView((current) => panBy(current, -event.deltaY, 0));
      } else {
        setView((current) => panBy(current, -event.deltaX, -event.deltaY));
      }
    };
    host.addEventListener("wheel", onWheel, { passive: false });
    return () => host.removeEventListener("wheel", onWheel);
  }, []);

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button === 1 || (event.button === 0 && spaceRef.current)) {
      event.preventDefault();
      userInteractedRef.current = true;
      dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
      event.currentTarget.setPointerCapture(event.pointerId);
      setPanning(true);
    }
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setView((current) => panBy(current, event.clientX - drag.x, event.clientY - drag.y));
    drag.x = event.clientX;
    drag.y = event.clientY;
  }

  function endDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
      setPanning(false);
    }
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    // event.code pins shortcuts to physical keys — `key` varies across
    // keyboard layouts (Shift+2 is "@" in US, `"` in es-CL).
    if (event.shiftKey && event.code === "Digit1") {
      event.preventDefault();
      fit();
    } else if (event.shiftKey && event.code === "Digit2") {
      event.preventDefault();
      if (selectionBox) {
        userInteractedRef.current = true;
        setView(fitTransform(selectionBox, size.w, size.h));
      }
    } else if (event.shiftKey && event.code === "Digit0") {
      event.preventDefault();
      userInteractedRef.current = true;
      setView((current) => zoomAt(current, size.w / 2, size.h / 2, SCALE_100 / current.scale));
    } else if (event.key === "ArrowLeft") {
      userInteractedRef.current = true;
      setView((current) => panBy(current, PAN_STEP, 0));
    } else if (event.key === "ArrowRight") {
      userInteractedRef.current = true;
      setView((current) => panBy(current, -PAN_STEP, 0));
    } else if (event.key === "ArrowUp") {
      userInteractedRef.current = true;
      setView((current) => panBy(current, 0, PAN_STEP));
    } else if (event.key === "ArrowDown") {
      userInteractedRef.current = true;
      setView((current) => panBy(current, 0, -PAN_STEP));
    }
  }

  const zoomStep = useCallback(
    (factor: number) => {
      userInteractedRef.current = true;
      setView((current) => zoomAt(current, size.w / 2, size.h / 2, factor));
    },
    [size.w, size.h],
  );

  const percent = Math.round((view.scale / SCALE_100) * 100);
  const menu = useMemo(
    () => [
      {
        label: `${t("canvas.zoomActual")} (100%)`,
        run: () => {
          userInteractedRef.current = true;
          setView((current) => zoomAt(current, size.w / 2, size.h / 2, SCALE_100 / current.scale));
        },
        disabled: false,
      },
      {
        label: t("canvas.fit"),
        run: fit,
        disabled: false,
      },
      {
        label: t("canvas.zoomSelection"),
        run: () => {
          if (selectionBox) {
            userInteractedRef.current = true;
            setView(fitTransform(selectionBox, size.w, size.h));
          }
        },
        disabled: !selectionBox,
      },
    ],
    [fit, selectionBox, size.w, size.h],
  );

  return (
    <div
      ref={hostRef}
      className={`canvas-viewport${panning ? " is-panning" : ""}`}
      role="application"
      aria-label={t("assembly.frontView")}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={onKeyDown}
    >
      {/* role="group" keeps the interactive member nodes in the AT tree —
          "img" would flatten 90+ focusable bays/members into one picture. */}
      <svg
        className="canvas-sheet"
        role="group"
        aria-label={t("assembly.frontView")}
        data-testid="assembly-sheet"
      >
        <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
          <ViewportScaleContext.Provider value={scaleContext}>
            {children}
          </ViewportScaleContext.Provider>
        </g>
      </svg>
      <div className="viewport-island" role="toolbar" aria-label={t("canvas.viewport")}>
        <button
          type="button"
          className="viewport-button"
          aria-label={t("canvas.zoomOut")}
          onClick={() => zoomStep(1 / 1.25)}
        >
          −
        </button>
        <button
          type="button"
          className="viewport-button viewport-button--percent"
          aria-label={t("canvas.zoomMenu")}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          {percent}%
        </button>
        <button
          type="button"
          className="viewport-button"
          aria-label={t("canvas.zoomIn")}
          onClick={() => zoomStep(1.25)}
        >
          +
        </button>
        {/* Fit lives on the island, not only in the % menu — after wheel-pan
         * the product can sit fully off-canvas and Encajar is the recovery. */}
        <button
          type="button"
          className="viewport-button"
          aria-label={t("canvas.fit")}
          title={t("canvas.fit")}
          onClick={fit}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path
              d="M1 4.5V1h3.5M7.5 1H11v3.5M11 7.5V11H7.5M4.5 11H1V7.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
            />
          </svg>
        </button>
        {menuOpen && (
          <div className="viewport-menu">
            {menu.map((item, index) => (
              <button
                key={`${item.label}-${index}`}
                type="button"
                className="viewport-menu__item"
                disabled={item.disabled}
                onClick={() => {
                  item.run();
                  setMenuOpen(false);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <output className="viewport-status" aria-live="off">
        {status}
      </output>
    </div>
  );
}
