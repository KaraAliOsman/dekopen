/** Playwright runner: per route × viewport × theme — screenshot + console +
 * HTTP + DOM probes feeding the pure detectors. */
import { chromium, type Browser, type BrowserContext, type Page } from "@playwright/test";

import {
  scanConsoleEntries,
  scanHttpEntries,
  scanLayout,
  scanStyles,
  scanVisibleText,
  type BoxProbe,
  type Finding,
} from "./detectors.ts";

export const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1024x768", width: 1024, height: 768 },
] as const;

export const MOBILE_VIEWPORT = { name: "390x844", width: 390, height: 844 } as const;

export const THEMES = ["light", "dark"] as const;

export type CaptureResult = {
  route: string;
  url: string;
  role: string;
  viewport: string;
  theme: string;
  screenshot: string;
  findings: Finding[];
  finalUrl: string;
};

const DOM_PROBE_JS = `() => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const texts = [];
  let node;
  while ((node = walker.nextNode())) {
    const v = node.nodeValue || "";
    const el = node.parentElement;
    if (!el) continue;
    // Los identificadores técnicos (SKU, códigos de error, nombres de campo)
    // viven en contextos code/mono — su texto no es voz de producto y no debe
    // disparar el escáner de vocabulario.
    if (el.closest("code, pre, samp, kbd, .fmt-code, .ui-code, [data-code]")) continue;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const trimmed = v.trim();
    if (trimmed) texts.push(trimmed);
  }
  const boxes = [];
  const densityOf = (el) => {
    const host = el.closest("[data-density]");
    return (
      (host && host.getAttribute("data-density")) ||
      document.documentElement.getAttribute("data-density") ||
      ""
    );
  };
  const bgOf = (el) => {
    // Compone las capas translúcidas sobre los ancestros: un
    // rgba(7,95,90,0.125) NO es un fondo opaco — WCAG mide contra el
    // color resultante de la composición, no el canal alfa ignorado.
    const parseBg = (bg) => {
      // Sin regex: este cuerpo se evalúa dentro de un template literal y
      // los backslashes no sobreviven (el ( literal rompería el parseo).
      const open = (bg || "").indexOf("(");
      const close = (bg || "").indexOf(")");
      if (open < 0 || close < 0 || close < open) return null;
      const parts = bg
        .slice(open + 1, close)
        .split(/[ ,/]+/)
        .filter((s) => s.length > 0)
        .map((s) => parseFloat(s));
      if (parts.length < 3 || parts.slice(0, 3).some((n) => !Number.isFinite(n))) return null;
      return [parts[0], parts[1], parts[2], parts.length > 3 && Number.isFinite(parts[3]) ? parts[3] : 1];
    };
    const composite = (top, under) => {
      const [tr, tg, tb, ta] = top;
      const [ur, ug, ub, ua] = under;
      const na = ta + ua * (1 - ta);
      if (na <= 0) return [0, 0, 0, 0];
      return [
        (tr * ta + ur * ua * (1 - ta)) / na,
        (tg * ta + ug * ua * (1 - ta)) / na,
        (tb * ta + ub * ua * (1 - ta)) / na,
        na,
      ];
    };
    let acc = null;
    let node = el;
    while (node && node !== document.documentElement) {
      const c = parseBg(getComputedStyle(node).backgroundColor);
      if (c && c[3] > 0) {
        acc = acc === null ? c : composite(acc, c);
        if (acc[3] >= 0.999) break;
      }
      node = node.parentElement;
    }
    const bodyC = parseBg(getComputedStyle(document.body).backgroundColor) || [255, 255, 255, 1];
    const final = acc === null ? bodyC : composite(acc, bodyC);
    return "rgb(" + Math.round(final[0]) + ", " + Math.round(final[1]) + ", " + Math.round(final[2]) + ")";
  };
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    // Contenido de un <svg aria-hidden> es decorativo (láminas de estados
    // vacíos, iconos): su «texto» nunca es legible por diseño — no audit.
    if (el.closest('svg[aria-hidden="true"]') !== null) continue;
    const tag = el.tagName.toLowerCase();
    const interactive =
      ["button", "a", "input", "select", "textarea", "summary"].includes(tag) ||
      (tag === "label" &&
        (el.querySelector("input, select, textarea") !== null ||
          el.getAttribute("for") !== null)) ||
      ["button", "link", "menuitem", "tab", "option", "checkbox", "radio", "switch", "combobox"].includes(
        el.getAttribute("role") || "",
      ) ||
      el.getAttribute("tabindex") !== null;
    const cls = (el.getAttribute("class") || "").toString();
    const regionHost = el.closest("[data-region]");
    const ownText = Array.from(el.childNodes)
      .filter((n) => n.nodeType === Node.TEXT_NODE)
      .map((n) => (n.nodeValue || "").trim())
      .filter(Boolean)
      .join(" ");
    const radii = [
      style.borderTopLeftRadius,
      style.borderTopRightRadius,
      style.borderBottomLeftRadius,
      style.borderBottomRightRadius,
    ].map((v) => parseFloat(v) || 0);
    boxes.push({
      label:
        tag + (el.id ? "#" + el.id : "") + " · " + (el.textContent || "").trim().slice(0, 40),
      fontPx: parseFloat(style.fontSize) || 0,
      widthPx: r.width,
      heightPx: r.height,
      interactive,
      radiusPx: Math.max(...radii),
      shadow: style.boxShadow,
      // El degradado prohibido es el decorativo en chrome de UI. Quedan
      // fuera: el interior de un <svg> (la vidriera se sombrea como
      // geometría, no como adorno) y la línea esquelética .ui-skeleton
      // (la ondulación ES el indicador de espera, idiomático).
      gradient:
        (style.backgroundImage || "").includes("gradient(") &&
        el.namespaceURI !== "http://www.w3.org/2000/svg" &&
        el.closest("svg, .ui-skeleton__line") === null,
      blur:
        (style.backdropFilter && style.backdropFilter !== "none") ||
        (style.filter || "").includes("blur("),
      color: ownText ? style.color : "",
      bgColor: ownText ? bgOf(el) : "",
      weight: parseFloat(style.fontWeight) || 400,
      text: ownText.slice(0, 60),
      // cursor:pointer se hereda: solo cuenta si ningún ancestro es
      // interactivo (un <path> dentro de un <button> no es «bare»).
      cursorPointer:
        style.cursor === "pointer" &&
        !interactive &&
        el.parentElement?.closest(
          "button, a, input, select, textarea, summary, [role], [tabindex], label",
        ) === null,
      primary: /primary/.test(cls) || el.getAttribute("data-variant") === "primary",
      region: regionHost ? regionHost.getAttribute("data-region") : "",
      workshop: densityOf(el) === "workshop",
      // WCAG exime los controles inactivos — y su contenido heredado: un
      // <span> dentro de un <button disabled> tampoco tiene que cumplir AA.
      disabled:
        el.matches(":disabled") ||
        el.getAttribute("aria-disabled") === "true" ||
        el.closest(
          ":disabled, [aria-disabled='true'], [disabled], fieldset:disabled",
        ) !== null,
    });
  }
  return {
    text: texts.join(" "),
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    boxes,
  };
}`;

async function captureOne(
  context: BrowserContext,
  url: string,
  meta: {
    route: string;
    role: string;
    viewport: string;
    theme: string;
    touchAudit: boolean;
    expectViolations?: boolean;
    toleratedHttpStatuses?: number[];
  },
  waitFor: string | undefined,
  shotDir: string,
): Promise<CaptureResult> {
  const page = await context.newPage();
  const consoleEntries: { level: string; text: string }[] = [];
  const httpEntries: { url: string; status: number }[] = [];
  page.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) {
      consoleEntries.push({ level: msg.type(), text: msg.text() });
    }
  });
  page.on("pageerror", (err) => {
    consoleEntries.push({ level: "error", text: `pageerror: ${err.message}` });
  });
  page.on("response", (res) => {
    if (res.status() >= 400) {
      httpEntries.push({ url: res.url(), status: res.status() });
    }
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  try {
    if (waitFor) await page.waitForSelector(waitFor, { timeout: 12_000 });
    await page.waitForLoadState("networkidle", { timeout: 15_000 });
  } catch {
    // settle timeout is itself evidence — capture anyway
  }
  await page.waitForTimeout(600);

  const probe = (await page.evaluate(`(${DOM_PROBE_JS})()`)) as {
    text: string;
    scrollWidth: number;
    clientWidth: number;
    boxes: BoxProbe[];
  };

  const findings: Finding[] = meta.expectViolations
    ? []
    : [
        ...scanVisibleText(probe.text),
        ...scanLayout(probe.scrollWidth, probe.clientWidth, probe.boxes, {
          touchAudit: meta.touchAudit,
        }),
        ...scanStyles(probe.boxes),
        ...scanConsoleEntries(
          consoleEntries.filter((e) => {
            // Un código tolerado por contrato tampoco debe contar como
            // error de consola: el navegador registra "Failed to load
            // resource: ... 410" aunque el 410 sea la respuesta esperada.
            const m = /status of (\d+)/.exec(e.text);
            return !(m && (meta.toleratedHttpStatuses ?? []).includes(Number(m[1])));
          }),
        ),
        ...scanHttpEntries(
          httpEntries.filter((e) => !(meta.toleratedHttpStatuses ?? []).includes(e.status)),
        ),
      ];

  const shotName = `${meta.route}--${meta.viewport}--${meta.theme}.png`;
  await page.screenshot({ path: `${shotDir}/${shotName}`, fullPage: false });
  const finalUrl = page.url();
  await page.close();
  return {
    route: meta.route,
    url,
    role: meta.role,
    viewport: meta.viewport,
    theme: meta.theme,
    screenshot: `shots/${shotName}`,
    findings,
    finalUrl,
  };
}

export async function runCaptures(args: {
  baseUrl: string;
  jobs: {
    route: string;
    url: string;
    role: string;
    waitFor?: string;
    extraMobile?: boolean;
    touchAudit?: boolean;
    expectViolations?: boolean;
    toleratedHttpStatuses?: number[];
  }[];
  storageStates: Record<string, string>;
  outDir: string;
}): Promise<CaptureResult[]> {
  const browser = await chromium.launch();
  const results: CaptureResult[] = [];
  try {
    for (const job of args.jobs) {
      const viewports: { name: string; width: number; height: number }[] = [...VIEWPORTS];
      if (job.extraMobile) viewports.push(MOBILE_VIEWPORT);
      for (const viewport of viewports) {
        for (const theme of THEMES) {
          const context = await browser.newContext({
            viewport: { width: viewport.width, height: viewport.height },
            colorScheme: theme,
            storageState: job.role === "public" ? undefined : args.storageStates[job.role],
            baseURL: args.baseUrl,
          });
          try {
            results.push(
              await captureOne(
                context,
                job.url,
                {
                  route: job.route,
                  role: job.role,
                  viewport: viewport.name,
                  theme,
                  touchAudit: job.touchAudit === true && viewport.name === MOBILE_VIEWPORT.name,
                  expectViolations: job.expectViolations,
                  toleratedHttpStatuses: job.toleratedHttpStatuses,
                },
                job.waitFor,
                `${args.outDir}/shots`,
              ),
            );
          } catch (error) {
            results.push({
              route: job.route,
              url: job.url,
              role: job.role,
              viewport: viewport.name,
              theme,
              screenshot: "",
              findings: [
                {
                  kind: "console-error",
                  detail: `capture crashed: ${String(error).slice(0, 160)}`,
                },
              ],
              finalUrl: "",
            });
          } finally {
            await context.close();
          }
        }
      }
    }
  } finally {
    await browser.close();
  }
  return results;
}
