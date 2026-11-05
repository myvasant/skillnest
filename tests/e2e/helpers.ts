import { expect, type Locator, type Page } from "@playwright/test";

/** Replace the contents of a CodeMirror editor inside `scope`. */
export async function typeCode(page: Page, scope: Locator, code: string) {
  const editor = scope.locator(".cm-content").first();
  await editor.click();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.press("Delete");
  // insertText bypasses auto-closing brackets so the code arrives exactly as written.
  await page.evaluate((text) => document.execCommand("insertText", false, text), code);
}

export async function waitForPythonReady(page: Page) {
  await expect(page.getByRole("status").filter({ hasText: /Python ready/ })).toBeVisible({ timeout: 60_000 });
}

export async function answerPredict(scope: Locator, answer: string) {
  await scope.getByRole("textbox").fill(answer);
  await scope.getByRole("button", { name: "Check prediction" }).click();
}

export async function answerMcq(scope: Locator, optionText: string | RegExp) {
  await scope.getByRole("radio", { name: optionText }).check();
  await scope.getByRole("button", { name: "Check answer" }).click();
}
