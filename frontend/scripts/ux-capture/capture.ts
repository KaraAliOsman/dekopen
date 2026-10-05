/** Playwright runner: per route × viewport × theme — screenshot + console +
 * HTTP + DOM probes feeding the pure detectors. */
import { chromium, type Browser, type BrowserContext, type Page } from "@playwright/test";

import {
  scanConsoleEntries,
  scanHttpEntries,
  scanLayout,
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
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const trimmed = v.trim();
    if (trimmed) texts.push(trimmed);
  }
  const boxes = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    const tag = el.tagName.toLowerCase();
    const interactive =
      ["button", "a", "input", "select", "textarea"].includes(tag) ||
      el.getAttribute("role") === "button" ||
      el.getAttribute("role") === "link" ||
      el.getAttribute("tabindex") !== null;
    const label =
      tag + (el.id ? "#" + el.id : "") + " · " + (el.textContent || "").trim().slice(0, 40);
    boxes.push({
      label,
      fontPx: parseFloat(style.fontSize) || 0,
      widthPx: r.width,
      heightPx: r.height,
      interactive,
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

  const findings: Finding[] = [
    ...scanVisibleText(probe.text),
    ...scanLayout(probe.scrollWidth, probe.clientWidth, probe.boxes, {
      touchAudit: meta.touchAudit,
    }),
    ...scanConsoleEntries(consoleEntries),
    ...scanHttpEntries(httpEntries),
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
