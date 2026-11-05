// Read-only, syntax-highlighted code using the same Lezer parser as the editor.
import { Fragment, useMemo, type ReactNode } from "react";
import { highlightCode, classHighlighter } from "@lezer/highlight";
import { parser as pythonParser } from "@lezer/python";
import { cn } from "./ui";

export function highlightPython(code: string): ReactNode[][] {
  const lines: ReactNode[][] = [[]];
  let key = 0;
  highlightCode(
    code,
    pythonParser.parse(code),
    classHighlighter,
    (text, classes) => {
      lines[lines.length - 1]!.push(
        classes ? (
          <span key={key++} className={classes}>
            {text}
          </span>
        ) : (
          <Fragment key={key++}>{text}</Fragment>
        ),
      );
    },
    () => lines.push([]),
  );
  return lines;
}

export function CodeView({
  code,
  language = "python",
  activeLine,
  errorLine,
  showLineNumbers = true,
  className,
  label,
}: {
  code: string;
  language?: string;
  activeLine?: number | null;
  errorLine?: number | null;
  showLineNumbers?: boolean;
  className?: string;
  label?: string;
}) {
  const trimmed = code.replace(/\n$/, "");
  const lines = useMemo(() => (language === "python" ? highlightPython(trimmed) : trimmed.split("\n").map((l) => [l])), [trimmed, language]);
  return (
    <pre
      className={cn("scrollbar-thin overflow-x-auto bg-code py-3 font-mono text-[13.5px] leading-[1.65] text-text", className)}
      aria-label={label ?? `${language} code`}
      tabIndex={0}
    >
      <code>
        {lines.map((parts, i) => {
          const n = i + 1;
          const active = activeLine === n;
          const error = errorLine === n;
          return (
            <div
              key={i}
              className={cn("flex min-w-max pr-4", active && "bg-warning-soft", error && "bg-danger-soft")}
              aria-current={active ? "step" : undefined}
            >
              {showLineNumbers && (
                <span className={cn("w-10 shrink-0 select-none pr-3 text-right text-faint", active && "font-semibold text-warning")} aria-hidden>
                  {active ? "➜" : n}
                </span>
              )}
              <span className={cn(!showLineNumbers && "pl-4")}>{parts.length ? parts : " "}</span>
            </div>
          );
        })}
      </code>
    </pre>
  );
}
