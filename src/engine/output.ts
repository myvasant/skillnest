// Output comparison used by exercises, predict-output questions and the content tests.

/** Normalise program output: unify newlines, drop trailing spaces per line and trailing blank lines. */
export function normalizeOutput(text: string): string {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.trimEnd())
    .join("\n")
    .replace(/\n+$/, "");
}

export function outputsMatch(actual: string, expected: string): boolean {
  return normalizeOutput(actual) === normalizeOutput(expected);
}

export type DiffLine = { kind: "same" | "missing" | "unexpected" | "changed"; expected?: string; actual?: string; line: number };

/** A simple line-by-line comparison (outputs in lessons are short, so no LCS is needed). */
export function diffOutput(actual: string, expected: string): DiffLine[] {
  const a = normalizeOutput(actual).split("\n");
  const e = normalizeOutput(expected).split("\n");
  const rows: DiffLine[] = [];
  const length = Math.max(a.length, e.length);
  for (let i = 0; i < length; i++) {
    const act = a[i];
    const exp = e[i];
    if (act === exp) rows.push({ kind: "same", expected: exp, actual: act, line: i + 1 });
    else if (act === undefined) rows.push({ kind: "missing", expected: exp, line: i + 1 });
    else if (exp === undefined) rows.push({ kind: "unexpected", actual: act, line: i + 1 });
    else rows.push({ kind: "changed", expected: exp, actual: act, line: i + 1 });
  }
  return rows;
}
