// Error cases, offline behaviour, keyboard access, small screens and theming.
import { expect, test } from "@playwright/test";
import { typeCode, waitForPythonReady } from "./helpers";

test("infinite loops are stopped and explained, and the runtime recovers", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/playground");
  await waitForPythonReady(page);
  const editor = page.locator(".gw-editor").first();
  await typeCode(page, editor, "n = 0\nwhile n < 10:\n    total = n\n");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText(/Stopped after 8 seconds/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("The program ran too long and was stopped")).toBeVisible();
  await waitForPythonReady(page);
  await typeCode(page, editor, "print('recovered')\n");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.locator("pre", { hasText: "recovered" })).toBeVisible();
});

test("runtime errors show a beginner explanation", async ({ page }) => {
  await page.goto("/learn/python.variables#mistakes");
  await waitForPythonReady(page);
  const example = page.locator("figure", { hasText: "print(subtotl)" });
  await example.getByRole("button", { name: "Run" }).click();
  await expect(example.locator("p", { hasText: "NameError: name 'subtotl' is not defined" })).toBeVisible();
  await expect(example.getByText(/Did you mean "subtotal"/)).toBeVisible();
});

test("unsupported packages fail with a clear message", async ({ page }) => {
  await page.goto("/playground");
  await waitForPythonReady(page);
  await typeCode(page, page.locator(".gw-editor").first(), "import definitely_not_a_module\n");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText("Module not available")).toBeVisible();
});

test("unknown lessons and routes show helpful pages", async ({ page }) => {
  await page.goto("/learn/does.not-exist");
  await expect(page.getByRole("heading", { name: "Lesson not found" })).toBeVisible();
  await page.goto("/no/such/page");
  await expect(page.getByText("Page not found")).toBeVisible();
});

test("core learning never contacts external hosts", async ({ page }) => {
  const external: string[] = [];
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.hostname === "localhost" || url.hostname === "127.0.0.1") return route.continue();
    external.push(url.href);
    return route.abort();
  });
  await page.goto("/");
  await page.goto("/learn/python.numbers");
  await waitForPythonReady(page);
  const example = page.locator("figure", { hasText: "print(0.1 + 0.2)" }).first();
  await example.getByRole("button", { name: "Run" }).click();
  await expect(example.getByText("0.30000000000000004")).toBeVisible();
  await page.goto("/curriculum");
  await page.goto("/settings");
  expect(external).toEqual([]);
});

test("keeps working when the network disconnects", async ({ page, context }) => {
  await page.goto("/learn/python.numbers");
  await waitForPythonReady(page);
  // The app warms every screen in the background; wait for that, then cut the network.
  await expect(page.locator("html")).toHaveAttribute("data-prefetched", "true", { timeout: 30_000 });
  await context.setOffline(true);
  await expect(page.getByText("Offline", { exact: true })).toBeVisible();
  const example = page.locator("figure", { hasText: "print(0.1 + 0.2)" }).first();
  await example.getByRole("button", { name: "Run" }).click();
  await expect(example.getByText("0.30000000000000004")).toBeVisible();
  // Screens already loaded in this session keep working without any network.
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await page.getByRole("link", { name: "Glossary" }).click();
  await expect(page.getByRole("heading", { name: "Glossary" })).toBeVisible();
  await page.getByRole("link", { name: "Curriculum" }).first().click();
  await expect(page.getByRole("heading", { name: "Curriculum" })).toBeVisible();
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("groundwork:progress")!).lessons["python.numbers"]);
  expect(saved).toBeTruthy();
  await context.setOffline(false);
});

test("search finds lessons, glossary terms and exercises from the keyboard", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("ControlOrMeta+K");
  const box = page.getByRole("combobox", { name: "Search query" });
  await expect(box).toBeFocused();
  await box.fill("floor division");
  await expect(page.getByRole("option").first()).toBeVisible();
  await box.fill("variables");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/learn\/python\.variables/);
});

test("keyboard users can skip to content and reach navigation", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main$/);
});

test("small screens use a navigation drawer", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("dialog", { name: "Navigation" }).getByRole("link", { name: "Glossary" }).click();
  await expect(page.getByRole("heading", { name: "Glossary" })).toBeVisible();
});

test("theme toggles and persists across reloads", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
});
