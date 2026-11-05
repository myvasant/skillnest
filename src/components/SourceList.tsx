import { CircleCheck, CircleHelp, ExternalLink, ShieldAlert } from "lucide-react";
import { curriculum } from "../content/runtime";
import type { Source } from "../content/schema";

/** Sources with honest link status: only URLs present in content/link-report.json are shown as checked. */
export function SourceList({ sources }: { sources: Source[] }) {
  return (
    <ul className="space-y-2 text-[14px]">
      {sources.map((s) => {
        const status = curriculum.links[s.url];
        const date = status ? new Date(status.checkedAt).toLocaleDateString() : null;
        return (
          <li key={s.url}>
            <a href={s.url} target="_blank" rel="noopener noreferrer" className="hover:text-accent">
              {s.title} <ExternalLink className="inline size-3 opacity-60" aria-label="(external)" />
            </a>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px] text-faint">
              {s.publisher && <span>{s.publisher}</span>}
              {s.version && <span>· version {s.version}</span>}
              {status?.ok && (
                <span className="inline-flex items-center gap-1 text-success" title="The link resolved when the link checker last ran. This does not mean the content was reviewed on that date.">
                  <CircleCheck className="size-3" aria-hidden /> link checked {date}
                </span>
              )}
              {status && !status.ok && status.verdict === "blocked" && (
                <span className="inline-flex items-center gap-1" title="The site refused the automated checker (bot protection); it may still work in a browser.">
                  <ShieldAlert className="size-3" aria-hidden /> not verifiable automatically
                </span>
              )}
              {status && !status.ok && status.verdict !== "blocked" && (
                <span className="inline-flex items-center gap-1 text-danger">
                  <ShieldAlert className="size-3" aria-hidden /> link failed on {date}
                </span>
              )}
              {!status && (
                <span className="inline-flex items-center gap-1">
                  <CircleHelp className="size-3" aria-hidden /> link not yet checked
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
