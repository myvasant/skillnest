// The complete first learning journey (README → "Vertical slice"):
// open → navigate → lesson → visualise → run code → exercise → feedback →
// fix a mistake → mastery check → persist → reopen → resume → recommendation →
// export → reset → import.
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { answerMcq, answerPredict, typeCode, waitForPythonReady } from "./helpers";

test("complete learning journey for Variables and Assignment", async ({ page }) => {
  // 1. Open the application: a new learner sees the welcome card and a first recommendation.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome to Groundwork" })).toBeVisible();

  // 2. Navigate to a Python topic through the curriculum.
  await page.getByRole("link", { name: "Curriculum" }).first().click();
  await page.getByRole("button", { name: /2\. Python/ }).click();
  await page.getByRole("tab", { name: "List" }).click();
  await page.getByRole("link", { name: "Variables and assignment" }).click();

  // 3. A beginner-friendly lesson with objectives and prerequisites.
  await expect(page.getByRole("heading", { level: 1, name: "Variables and Assignment" })).toBeVisible();
  await expect(page.getByText("You will be able to")).toBeVisible();
  await expect(page.getByText("Before you start")).toBeVisible();
  await waitForPythonReady(page);

  // 4. Understand through a visualisation: step through an assignment.
  const tracer = page.locator("figure", { hasText: "Step through an assignment" });
  await tracer.getByRole("button", { name: "Start step-through" }).click();
  await expect(tracer.getByText("Step 1 /")).toBeVisible();
  for (let i = 0; i < 3; i++) await tracer.getByRole("button", { name: /^Next/ }).click();
  await expect(tracer.getByLabel("Frames", { exact: true })).toContainText("total");
  await expect(tracer.getByLabel("Objects", { exact: true })).toContainText("60");

  // 5. Edit and run Python code.
  const example = page.locator("figure", { hasText: "balance += 250" });
  await example.getByRole("button", { name: "Run" }).click();
  await expect(example.getByText("1150")).toBeVisible();

  // 6–8. Exercise: a wrong attempt gets targeted feedback, then the learner fixes it.
  const exercise = page.locator("#item-total-price");
  await exercise.scrollIntoViewIfNeeded();
  await typeCode(page, exercise, 'price = 45\nquantity = 4\ntotal = 180\nprint("total")\n');
  await exercise.getByRole("button", { name: "Check my code" }).click();
  await expect(exercise.getByText("Calculate total from price and quantity")).toBeVisible();
  await expect(exercise.getByText("Common mistake")).toBeVisible();
  await expect(exercise.getByText("Expected vs. your output")).toBeVisible();
  await typeCode(page, exercise, "price = 45\nquantity = 4\ntotal = price * quantity\nprint(total)\n");
  await exercise.getByRole("button", { name: "Check my code" }).click();
  await expect(exercise.getByText("All checks passed.")).toBeVisible();

  // A misconception in a prediction question gets a specific explanation.
  const alias = page.locator("#item-predict-alias");
  await answerPredict(alias, "20 20");
  await expect(alias.getByText(/linked variables/i)).toBeVisible();

  // 9. Mastery check with new items, one attempt each.
  const check = page.locator("#mastery-check");
  await check.scrollIntoViewIfNeeded();
  await check.getByRole("button", { name: "Start mastery check" }).click();
  await answerPredict(check.locator("#item-m-predict-chain"), "8 4");
  await answerMcq(check.locator("#item-m-first-line-error"), /NameError, because total is read/);
  await check.locator("#item-m-types").getByRole("button", { name: "False" }).click();
  const receipt = check.locator("#item-m-receipt");
  await typeCode(page, receipt, "ticket = 250\nsnack = 120\npeople = 3\nbill = (ticket + snack) * people\nbill -= 100\nprint(bill)\n");
  await receipt.getByRole("button", { name: "Submit answer" }).click();
  await expect(receipt.getByText("All checks passed.")).toBeVisible();
  const swap = check.locator("#item-m-debug-swap");
  await typeCode(page, swap, 'first = "A"\nsecond = "B"\nfirst, second = second, first\nprint(first, second)\n');
  await swap.getByRole("button", { name: "Submit answer" }).click();
  await expect(check.getByText("Variables and Assignment: mastered")).toBeVisible();
  await expect(check.getByText(/first spaced review is scheduled for tomorrow/)).toBeVisible();

  // 10–12. Progress is saved locally; close and reopen the app.
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("groundwork:progress") ?? "{}"));
  expect(saved.concepts["python.variables"].masteredAt).toBeTruthy();
  await page.goto("about:blank");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByText("Last visited:")).toBeVisible();

  // 13. A sensible, explained recommendation. Variables is mastered; its prerequisite lesson was never opened.
  const card = page.locator("main").getByText(/^Why:/).first();
  await expect(card).toBeVisible();
  await expect(page.getByText("Mastered", { exact: true }).first()).toBeVisible();
  await expect(page.locator("main")).toContainText("Variables and Assignment");

  // 14. Export progress, reset, then restore it from the file.
  await page.getByRole("link", { name: "Settings" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export progress" }).click();
  const download = await downloadPromise;
  const file = await download.path();
  const exported = JSON.parse(readFileSync(file, "utf8"));
  expect(exported.format).toBe("groundwork-progress");

  await page.getByLabel(/Type RESET to confirm/).fill("RESET");
  await page.getByRole("button", { name: "Delete my progress" }).click();
  await expect(page.getByText("All progress was reset.")).toBeVisible();
  expect(await page.evaluate(() => Object.keys(JSON.parse(localStorage.getItem("groundwork:progress")!).concepts).length)).toBe(0);

  await page.getByTestId("import-input").setInputFiles(file);
  await expect(page.getByText(/Replace your current progress/)).toBeVisible();
  await expect(page.getByText(/1 concepts mastered|1 concept/)).toBeVisible();
  await page.getByRole("button", { name: "Replace and restore" }).click();
  await expect(page.getByText("Progress restored from the backup file.")).toBeVisible();
  const restored = await page.evaluate(() => JSON.parse(localStorage.getItem("groundwork:progress")!));
  expect(restored.concepts["python.variables"].masteredAt).toBe(saved.concepts["python.variables"].masteredAt);

  // The restored state drives the dashboard again.
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});

test("after mastering the first two lessons the next concept is recommended with a reason", async ({ page }) => {
  await page.goto("/learn/python.first-program#mastery-check");
  await waitForPythonReady(page);
  const check = page.locator("#mastery-check");
  await check.getByRole("button", { name: "Start mastery check" }).click();
  await answerPredict(check.locator("#item-m-predict-order"), "A 1\nC 3\nDE");
  await answerMcq(check.locator("#item-m-which-error"), /Line 2 — a NameError/);
  const banner = check.locator("#item-m-code-banner");
  await typeCode(page, banner, 'print("==========")\nprint("Groundwork", 2026)\nprint("==========")\n');
  await banner.getByRole("button", { name: "Submit answer" }).click();
  await check.locator("#item-tf-syntax").getByRole("button", { name: "False" }).click();
  await expect(check.getByText("Your First Python Program: mastered")).toBeVisible();
  await expect(check.getByRole("link", { name: /Next: Variables and assignment/ })).toBeVisible();
  await expect(check.getByText(/builds on Your first program/)).toBeVisible();
});
