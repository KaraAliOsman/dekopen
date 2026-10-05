/** Auditoría axe del muestrario `/dev/ui` — los dos temas y las tres
 * densidades. Falla con cualquier violación `serious` o `critical`:
 * el muestrario es la referencia del sistema, si él no pasa AA los
 * encargos siguientes no tienen piso.
 *
 * Uso: UX_BASE_URL=http://127.0.0.1:5173 npm run ux:axe
 */
import { AxeBuilder } from "@axe-core/playwright";
import { chromium } from "@playwright/test";

const BASE = process.env.UX_BASE_URL ?? "http://127.0.0.1:5173";
const ROUTES = ["/dev/ui", "/dev/ui/mal"];
const THEMES = ["light", "dark"] as const;
const DENSITIES = ["office", "document", "workshop"] as const;

const browser = await chromium.launch();
let failures = 0;
try {
  for (const route of ROUTES) {
    for (const theme of THEMES) {
      for (const density of DENSITIES) {
        const context = await browser.newContext({ colorScheme: theme });
        const page = await context.newPage();
        await page.goto(`${BASE}${route}`, { waitUntil: "networkidle" });
        await page.evaluate(
          ({ theme: t, density: d }) => {
            const host = document.querySelector(".dev-ui");
            host?.setAttribute("data-theme-scope", t);
            host?.setAttribute("data-density", d);
          },
          { theme, density },
        );
        const results = await new AxeBuilder({ page }).analyze();
        const bad = results.violations.filter(
          (v) => v.impact === "serious" || v.impact === "critical",
        );
        if (bad.length) {
          failures += bad.length;
          for (const v of bad) {
            console.log(
              `[${v.impact}] ${route} ${theme}/${density} ${v.id}: ${v.help} — ${v.nodes.length} nodos`,
            );
            for (const node of v.nodes.slice(0, 5)) {
              console.log(`    ${node.target.join(" ")}`);
            }
          }
        }
        await context.close();
      }
    }
  }
} finally {
  await browser.close();
}

if (failures > 0) {
  console.error(`ux:axe: ${failures} violaciones serious/critical`);
  process.exit(1);
}
console.log("ux:axe: /dev/ui sin violaciones serious ni critical");
