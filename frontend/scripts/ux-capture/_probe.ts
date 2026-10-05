import { chromium } from "playwright";
const b = await chromium.launch(); const p = await b.newPage({viewport:{width:1280,height:800}});
await p.goto("http://127.0.0.1:5173/dev/ui"); await p.waitForSelector(".dev-ui");
const bad = await p.evaluate(() => {
  const out: string[] = [];
  document.querySelectorAll("*").forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.right > 1280.5 || r.width > 1280) out.push(`${el.tagName}.${(el as HTMLElement).className} w=${Math.round(r.width)} right=${Math.round(r.right)}`);
  });
  return out.slice(0, 25);
});
console.log(bad.join("\n")); await b.close();
