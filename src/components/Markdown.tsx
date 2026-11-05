// Markdown renderer for curriculum text. Renders to React elements (no raw
// HTML), so content cannot inject scripts. Internal links use custom schemes:
//   [text](concept:python.variables)  [text](lesson:python.variables)
//   [text](glossary:variable)          [text](project:calculator)
import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link } from "react-router";
import { ExternalLink } from "lucide-react";
import { curriculum } from "../content/runtime";
import { CodeView } from "./CodeView";
import { cn } from "./ui";

const INTERNAL = /^(concept|lesson|glossary|project|interview):(.+)$/;

function internalHref(kind: string, id: string): string {
  switch (kind) {
    case "concept": {
      const lessonId = curriculum.concepts[id]?.lessonId;
      return lessonId ? `/learn/${lessonId}` : `/concept/${id}`;
    }
    case "lesson":
      return `/learn/${id}`;
    case "glossary":
      return `/glossary#${id}`;
    case "project":
      return `/projects/${id}`;
    default:
      return `/interview?q=${id}`;
  }
}

const components: Components = {
  a({ href = "", children }) {
    const m = INTERNAL.exec(href);
    if (m) {
      const [, kind, id] = m;
      if (kind === "glossary") {
        const term = curriculum.glossary.find((g) => g.id === id);
        return (
          <Link to={internalHref(kind!, id!)} title={term?.definition} className="decoration-dotted">
            {children}
          </Link>
        );
      }
      return <Link to={internalHref(kind!, id!)}>{children}</Link>;
    }
    if (href.startsWith("/") || href.startsWith("#")) return <Link to={href}>{children}</Link>;
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
        <ExternalLink className="ml-0.5 inline size-3 align-[-1px] opacity-70" aria-label="(opens in a new tab)" />
      </a>
    );
  },
  pre({ children }) {
    return <>{children}</>;
  },
  code({ className, children }) {
    const lang = /language-(\w+)/.exec(className ?? "")?.[1];
    const text = String(children ?? "");
    if (!lang && !text.includes("\n")) return <code>{children}</code>;
    return (
      <div className="overflow-hidden rounded-lg border border-border">
        <CodeView code={text} language={lang ?? "text"} showLineNumbers={false} />
      </div>
    );
  },
};

const allowUrl = (url: string) => (INTERNAL.test(url) || /^(https?:|mailto:|\/|#)/.test(url) ? url : "");

export const Markdown = memo(function Markdown({ children, className, inline }: { children: string; className?: string; inline?: boolean }) {
  return (
    <div className={cn("prose-gw", inline && "[&>p]:inline", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} urlTransform={allowUrl}>
        {children}
      </ReactMarkdown>
    </div>
  );
});
