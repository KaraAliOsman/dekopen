import { chromium, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { detectTextFindings, summarizeFindings } from "./detectors.ts";
import {
  FIXTURE_USERS,
  THEMES,
  VIEWPORTS,
  routesForFixture,
  type FixtureRefs,
  type RouteDefinition,
  type UxRole,
} from "./routes.ts";

type Args = {
  out: string;
  routes?: string;
  roles?: UxRole[];
};

type AuthSession = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  expires_at?: number;
  token_type: string;
  user: { id: string };
};

type CaptureRecord = {
  routeId: string;
  path: string;
  role: string;
  theme: string;
  viewport: string;
  screenshot: string;
  overflowX: boolean;
  consoleErrors: string[];
  httpErrors: { url: string; status: number }[];
  findings: { kind: string; match?: string; sample?: string }[];
};

const baseUrl = process.env.UX_CAPTURE_BASE_URL ?? "http://127.0.0.1:5173";
const supabaseUrl =
  process.env.SUPABASE_URL ?? process.env.VITE_SUPABASE_URL ?? "http://127.0.0.1:25321";
const anonKey = process.env.SUPABASE_ANON_KEY ?? process.env.VITE_SUPABASE_ANON_KEY ?? "";
const djangoUrl = process.env.DJANGO_URL ?? "http://127.0.0.1:8000";
const organizationId = process.env.DEKOPEN_FIXTURE_ORG_ID ?? "548b9ce5-746b-5a4a-9127-733c4dcd0582";

function parseArgs(argv: string[]): Args {
  const args: Args = { out: "docs/redesign/captures/ux-run" };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === "--out") args.out = argv[++index] ?? args.out;
    else if (item === "--routes") args.routes = argv[++index];
    else if (item === "--roles") {
      args.roles = (argv[++index] ?? "")
        .split(",")
        .map((role) => role.trim())
        .filter((role): role is UxRole => role in FIXTURE_USERS);
    }
  }
  return args;
}

async function waitForHttp(url: string, timeoutMs = 30_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2_000) });
      if (response.status < 500) return true;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  return false;
}

async function ensureVite(): Promise<ChildProcess | null> {
  if (await waitForHttp(baseUrl, 2_000)) return null;
  const npmCli = path.join(
    path.dirname(process.execPath),
    "node_modules",
    "npm",
    "bin",
    "npm-cli.js",
  );
  const child = spawn(process.execPath, [npmCli, "run", "dev", "--", "--host", "127.0.0.1"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      VITE_SUPABASE_URL: supabaseUrl,
      VITE_SUPABASE_ANON_KEY: anonKey,
    },
    stdio: "ignore",
  });
  if (!(await waitForHttp(baseUrl, 45_000))) {
    child.kill();
    throw new Error(`Vite did not become ready at ${baseUrl}`);
  }
  return child;
}

async function signIn(role: UxRole): Promise<AuthSession> {
  const user = FIXTURE_USERS[role];
  const response = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: anonKey, "Content-Type": "application/json" },
    body: JSON.stringify({ email: user.email, password: user.password }),
  });
  if (!response.ok) {
    throw new Error(`Could not sign in ${role}: HTTP ${response.status} ${await response.text()}`);
  }
  return (await response.json()) as AuthSession;
}

async function authenticatedFetch<T>(session: AuthSession, apiPath: string): Promise<T> {
  const response = await fetch(`${djangoUrl}/api/v1${apiPath}`, {
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      "X-Organization-ID": organizationId,
    },
  });
  if (!response.ok) throw new Error(`GET ${apiPath} -> ${response.status}`);
  return (await response.json()) as T;
}

async function discoverFixture(session: AuthSession): Promise<FixtureRefs> {
  const projects = await authenticatedFetch<{ items: { id: string; name: string }[] }>(
    session,
    "/projects/",
  );
  const project =
    projects.items.find((item) => /casa|vivienda|fixture/i.test(item.name)) ?? projects.items[0];
  if (!project) throw new Error("Fixture has no project; run scripts/dev_fixture.py first");
  const detail = await authenticatedFetch<{
    positions?: { id: string }[];
    items?: { id: string }[];
  }>(session, `/projects/${project.id}/`);
  const positionId = detail.positions?.[0]?.id ?? detail.items?.[0]?.id ?? "missing-position";
  let clientId = process.env.DEKOPEN_UX_CLIENT_ID ?? "missing-client";
  try {
    const clients = await authenticatedFetch<{ items: { id: string }[] }>(session, "/clients/");
    clientId = clients.items[0]?.id ?? clientId;
  } catch {
    // Clients are still covered by /clients when detail discovery is unavailable.
  }
  return {
    projectId: process.env.DEKOPEN_UX_PROJECT_ID ?? project.id,
    positionId: process.env.DEKOPEN_UX_POSITION_ID ?? positionId,
    clientId,
    quoteTokens: {
      vigente: process.env.DEKOPEN_UX_QUOTE_VIGENTE ?? "fixture-vigente",
      aprobada: process.env.DEKOPEN_UX_QUOTE_APROBADA ?? "fixture-aprobada",
      revocada: process.env.DEKOPEN_UX_QUOTE_REVOCADA ?? "fixture-revocada",
      expirada: process.env.DEKOPEN_UX_QUOTE_EXPIRADA ?? "fixture-expirada",
      reemplazada: process.env.DEKOPEN_UX_QUOTE_REEMPLAZADA ?? "fixture-reemplazada",
    },
  };
}

function globMatches(value: string, glob?: string): boolean {
  if (!glob) return true;
  const pattern = new RegExp(
    `^${glob
      .split("*")
      .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join(".*")}$`,
  );
  return pattern.test(value);
}

async function prepareContext(
  browser: Browser,
  role: UxRole,
  theme: string,
  viewport: { width: number; height: number },
  publicRoute: boolean,
): Promise<BrowserContext> {
  const context = await browser.newContext({ baseURL: baseUrl, viewport });
  await context.addInitScript(
    ({ selectedTheme }) => {
      window.localStorage.setItem("dekopen.theme", selectedTheme);
    },
    { selectedTheme: theme },
  );
  if (!publicRoute) {
    const session = await signIn(role);
    await context.addInitScript(
      ({ authSession, orgId }) => {
        window.localStorage.setItem(`dekopen.active_org.${authSession.user.id}`, orgId);
        window.location.hash = "";
      },
      { authSession: session, orgId: organizationId },
    );
    const page = await context.newPage();
    const expiresAt = session.expires_at ?? Math.floor(Date.now() / 1000) + session.expires_in;
    await page.goto(
      `/auth/callback#access_token=${session.access_token}&refresh_token=${session.refresh_token}&expires_in=${session.expires_in}&expires_at=${expiresAt}&token_type=${session.token_type}&type=magiclink`,
    );
    await page.waitForFunction(() =>
      Object.keys(window.localStorage).some(
        (key) => key.startsWith("sb-") && key.endsWith("-auth-token"),
      ),
    );
    await page.close();
  }
  return context;
}

async function collectPresentationFindings(
  page: Page,
  workshop: boolean,
): Promise<{ kind: string; sample: string }[]> {
  return page.evaluate((needsTouchTargets) => {
    function visible(element: Element): boolean {
      const style = window.getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return (
        style.visibility !== "hidden" && style.display !== "none" && box.width > 0 && box.height > 0
      );
    }
    const findings: { kind: string; sample: string }[] = [];
    for (const element of Array.from(document.body.querySelectorAll("*"))) {
      if (!visible(element)) continue;
      const text = (element.textContent ?? "").trim();
      if (text && Number.parseFloat(window.getComputedStyle(element).fontSize) < 11) {
        findings.push({ kind: "font-under-11", sample: text.slice(0, 120) });
      }
      if (
        needsTouchTargets &&
        element instanceof HTMLElement &&
        (element.matches("button,a,input,select,textarea,[role='button']") || element.tabIndex >= 0)
      ) {
        const box = element.getBoundingClientRect();
        if (box.width < 44 || box.height < 44) {
          findings.push({
            kind: "touch-target-under-44",
            sample: `${element.tagName.toLowerCase()} ${text.slice(0, 80)}`,
          });
        }
      }
    }
    return findings;
  }, workshop);
}

async function captureRoute(
  context: BrowserContext,
  route: RouteDefinition,
  role: UxRole,
  theme: string,
  viewportId: string,
  outDir: string,
): Promise<CaptureRecord> {
  const page = await context.newPage();
  const consoleErrors: string[] = [];
  const httpErrors: { url: string; status: number }[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      httpErrors.push({ url: response.url(), status: response.status() });
    }
  });
  await page.goto(route.path, { waitUntil: "networkidle", timeout: 45_000 });
  await page.waitForTimeout(350);
  const text = await page
    .locator("body")
    .innerText({ timeout: 5_000 })
    .catch(() => "");
  const overflowX = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  const findings = [
    ...detectTextFindings(text),
    ...(await collectPresentationFindings(
      page,
      route.workshop || role === "OPERATOR" || role === "INSTALLER",
    )),
  ];
  const screenshot = `${route.id}__${role}__${theme}__${viewportId}.png`;
  await page.screenshot({ path: path.join(outDir, screenshot), fullPage: true });
  await page.close();
  return {
    routeId: route.id,
    path: route.path,
    role,
    theme,
    viewport: viewportId,
    screenshot,
    overflowX,
    consoleErrors,
    httpErrors,
    findings,
  };
}

function htmlReport(records: readonly CaptureRecord[]): string {
  const items = records
    .map(
      (record) => `<article>
<h2>${record.routeId} · ${record.role} · ${record.theme} · ${record.viewport}</h2>
<img src="./${record.screenshot}" loading="lazy" width="240">
<p>${record.path}</p>
<p>Hallazgos: ${record.findings.length} · HTTP >=400: ${record.httpErrors.length} · consola: ${record.consoleErrors.length} · overflow: ${record.overflowX}</p>
</article>`,
    )
    .join("\n");
  return `<!doctype html><meta charset="utf-8"><title>DEKOPEN ux:capture</title><style>body{font-family:system-ui;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}article{border:1px solid #ccc;padding:12px}img{max-width:100%;border:1px solid #ddd}</style><main>${items}</main>`;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const outDir = path.resolve(args.out);
  await mkdir(outDir, { recursive: true });
  const vite = await ensureVite();
  const browser = await chromium.launch({ headless: true });
  const estimator = await signIn("ESTIMATOR");
  const refs = await discoverFixture(estimator);
  const selectedRoles = new Set(args.roles ?? Object.keys(FIXTURE_USERS));
  const routes = routesForFixture(refs).filter(
    (route) => globMatches(route.id, args.routes) || globMatches(route.path, args.routes),
  );
  const records: CaptureRecord[] = [];
  try {
    for (const route of routes) {
      const roles = route.public ? [route.roles[0] ?? "ESTIMATOR"] : route.roles;
      for (const role of roles.filter((item) => selectedRoles.has(item))) {
        for (const theme of THEMES) {
          for (const viewport of VIEWPORTS) {
            const context = await prepareContext(
              browser,
              role,
              theme,
              viewport,
              Boolean(route.public),
            );
            records.push(await captureRoute(context, route, role, theme, viewport.id, outDir));
            await context.close();
          }
        }
      }
    }
  } finally {
    await browser.close();
    if (vite) vite.kill();
  }
  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    records,
    topFindings: summarizeFindings(records).slice(0, 30),
  };
  await writeFile(path.join(outDir, "report.json"), JSON.stringify(report, null, 2));
  await writeFile(path.join(outDir, "index.html"), htmlReport(records));
}

await main();
