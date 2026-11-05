// Automated WCAG 2.1 A/AA checks (axe-core) on the main screens, in light and
// dark themes. Automated checks find a subset of issues (contrast, labels,
// roles, landmarks); manual review with a screen reader is still needed.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const pages = [
  { name: "dashboard", path: "/" },
  { name: "lesson", path: "/learn/python.variables" },
  { name: "curriculum (graph)", path: "/curriculum?stage=python" },
  { name: "curriculum (list)", path: "/curriculum?stage=python&view=list" },
  { name: "concept outline", path: "/concept/rag.chunking" },
  { name: "paths", path: "/paths" },
  { name: "playground", path: "/playground" },
  { name: "visual explorer", path: "/visualize?v=http-lifecycle" },
  { name: "projects", path: "/projects" },
  { name: "interview", path: "/interview" },
  { name: "glossary", path: "/glossary" },
  { name: "settings", path: "/settings" },
];

for (const scheme of ["light", "dark"] as const) {
  for (const p of pages) {
    test(`${p.name} has no serious accessibility violations (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.goto(p.path);
      await page.locator("main h1").first().waitFor();
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      const report = serious.map((v) => `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join("\n  ")}`).join("\n");
      expect(serious, report).toEqual([]);
    });
  }
}
