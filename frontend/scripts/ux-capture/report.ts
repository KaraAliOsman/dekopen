/** report.json + thumbnail index.html writer for ux:capture runs. */
import { writeFileSync } from "node:fs";
import type { CaptureResult } from "./capture.ts";

export function writeReport(outDir: string, results: CaptureResult[]) {
  const byRoute = new Map<string, CaptureResult[]>();
  for (const r of results) {
    const list = byRoute.get(r.route) ?? [];
    list.push(r);
    byRoute.set(r.route, list);
  }
  const summary = {
    generated_at: new Date().toISOString(),
    routes: results.length,
    routes_with_findings: [...byRoute.entries()]
      .filter(([, rs]) => rs.some((r) => r.findings.length > 0))
      .map(([name]) => name),
    total_findings: results.reduce((n, r) => n + r.findings.length, 0),
  };
  writeFileSync(`${outDir}/report.json`, JSON.stringify({ summary, results }, null, 2));

  const cards = [...byRoute.entries()]
    .map(([route, rs]) => {
      const count = rs.reduce((n, r) => n + r.findings.length, 0);
      const badge = count === 0 ? "ok" : count < 4 ? "warn" : "bad";
      const thumbs = rs
        .filter((r) => r.screenshot)
        .map(
          (r) => `
        <figure>
          <img src="${r.screenshot}" loading="lazy" alt="${r.route} ${r.viewport} ${r.theme}" />
          <figcaption>${r.viewport} · ${r.theme}${r.findings.length ? ` · <b>${r.findings.length}</b>` : ""}</figcaption>
        </figure>`,
        )
        .join("\n");
      const details = rs
        .flatMap((r) =>
          r.findings.map(
            (f) =>
              `<li><code>${r.viewport}/${r.theme}</code> <b>${f.kind}</b> ${escapeHtml(f.detail)}</li>`,
          ),
        )
        .join("\n");
      return `
  <section class="card ${badge}">
    <h2>${route} <span class="role">${rs[0]?.role ?? ""}</span>
      <span class="count">${count === 0 ? "limpio" : `${count} hallazgos`}</span></h2>
    <div class="thumbs">${thumbs}</div>
    ${details ? `<ul class="findings">${details}</ul>` : ""}
  </section>`;
    })
    .join("\n");

  const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>ux:capture — ${summary.generated_at.slice(0, 10)}</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; margin: 2rem; }
  h1 { font-size: 1.4rem; }
  .card { border: 1px solid #8884; border-radius: 10px; padding: 1rem; margin-bottom: 1.2rem; }
  .card.ok { border-left: 4px solid #3a9; }
  .card.warn { border-left: 4px solid #da3; }
  .card.bad { border-left: 4px solid #d55; }
  h2 { font-size: 1rem; display: flex; gap: .6rem; align-items: baseline; }
  .role { color: #888; font-size: .8rem; font-weight: 400; }
  .count { margin-left: auto; font-size: .8rem; font-weight: 400; color: #888; }
  .thumbs { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: .6rem; }
  figure { margin: 0; }
  img { width: 100%; border: 1px solid #8884; border-radius: 6px; }
  figcaption { font-size: .72rem; color: #777; }
  .findings { font-size: .8rem; max-height: 12rem; overflow: auto; }
  .findings code { background: #8882; padding: 0 .3em; border-radius: 4px; }
</style>
</head>
<body>
<h1>ux:capture — ${summary.generated_at}</h1>
<p>${summary.routes} capturas · ${summary.total_findings} hallazgos · ${summary.routes_with_findings.length} rutas con hallazgos</p>
${cards}
</body>
</html>`;
  writeFileSync(`${outDir}/index.html`, html);
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
