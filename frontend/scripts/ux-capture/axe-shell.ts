/** Auditoría axe del shell por rol (P03): «Hoy» en los 5 roles × los dos
 * temas. Falla con cualquier violación `serious` o `critical`. Reusa los
 * storageStates que un ux:capture previo dejó en `.auth/<role>.json`.
 *
 *   UX_BASE_URL=http://127.0.0.1:5173 npm run ux:axe-shell
 */
import { AxeBuilder } from "@axe-core/playwright";
import { chromium } from "@playwright/test";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.UX_BASE_URL ?? "http://127.0.0.1:5173";
const ROLES = ["owner", "estimator", "manager", "operator", "installer"];
const THEMES = ["light", "dark"] as const;

const browser = await chromium.launch();
let failures = 0;
try {
  for (const role of ROLES) {
    const statePath = join(HERE, ".auth", `${role}.json`);
    if (!existsSync(statePath)) {
      console.error(`falta ${statePath} — corre ux:capture primero`);
      process.exit(1);
    }
    for (const theme of THEMES) {
      const context = await browser.newContext({
        colorScheme: theme,
        storageState: statePath,
        viewport: { width: 1440, height: 900 },
      });
      const page = await context.newPage();
      await page.goto(`${BASE}/dashboard`, { waitUntil: "networkidle" });
      const results = await new AxeBuilder({ page }).analyze();
      const bad = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      if (bad.length) {
        failures += bad.length;
        for (const v of bad) {
          console.log(
            `[${v.impact}] ${role}/${theme} ${v.id}: ${v.help} — ${v.nodes.length} nodos`,
          );
          for (const node of v.nodes.slice(0, 5)) {
            console.log(`    ${node.target.join(" ")}`);
          }
        }
      }
      await context.close();
    }
  }
} finally {
  await browser.close();
}

if (failures) {
  console.error(`ux:axe-shell: ${failures} violaciones serious/critical`);
  process.exit(1);
}
console.log("ux:axe-shell: /dashboard en 5 roles sin violaciones serious ni critical");
