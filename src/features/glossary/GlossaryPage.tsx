import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router";
import { Search } from "lucide-react";
import { curriculum } from "../../content/runtime";
import { Markdown } from "../../components/Markdown";
import { Card, PageHeader, cn } from "../../components/ui";
import { useDocumentTitle } from "../../lib/hooks";

export function GlossaryPage() {
  useDocumentTitle("Glossary");
  const location = useLocation();
  const [filter, setFilter] = useState("");
  const anchor = location.hash.slice(1);

  useEffect(() => {
    if (anchor) setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ block: "center" }), 50);
  }, [anchor]);

  const terms = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return curriculum.glossary.filter(
      (t) => !q || t.term.toLowerCase().includes(q) || t.aliases.some((a) => a.toLowerCase().includes(q)) || t.definition.toLowerCase().includes(q),
    );
  }, [filter]);

  const groups = useMemo(() => {
    const map = new Map<string, typeof terms>();
    for (const t of terms) {
      const letter = /[a-z]/i.test(t.term[0]!) ? t.term[0]!.toUpperCase() : "#";
      map.set(letter, [...(map.get(letter) ?? []), t]);
    }
    return [...map.entries()];
  }, [terms]);

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Glossary" description={`${curriculum.glossary.length} terms, each linked to the concept that explains it in depth.`} />
      <label className="mb-6 flex h-10 items-center gap-2 rounded-lg border border-border bg-surface px-3 shadow-card">
        <Search className="size-4 text-muted" aria-hidden />
        <span className="sr-only">Filter terms</span>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter terms…"
          className="flex-1 bg-transparent text-[14px] outline-none"
        />
      </label>
      <nav aria-label="Letters" className="mb-6 flex flex-wrap gap-1">
        {groups.map(([letter]) => (
          <a key={letter} href={`#letter-${letter}`} className="rounded px-2 py-0.5 text-[13px] font-medium text-muted hover:bg-surface-2 hover:text-text">
            {letter}
          </a>
        ))}
      </nav>
      <div className="space-y-8">
        {groups.map(([letter, items]) => (
          <section key={letter} aria-labelledby={`letter-${letter}`}>
            <h2 id={`letter-${letter}`} className="mb-2 text-lg font-semibold text-faint">
              {letter}
            </h2>
            <Card>
              <dl className="divide-y divide-border">
                {items.map((t) => {
                  const concept = t.concept ? curriculum.concepts[t.concept] : undefined;
                  return (
                    <div key={t.id} id={t.id} className={cn("scroll-mt-24 px-5 py-3.5", anchor === t.id && "bg-accent-soft/60")}>
                      <dt className="font-semibold">
                        {t.term}
                        {t.aliases.length > 0 && <span className="ml-2 text-[12.5px] font-normal text-muted">also: {t.aliases.join(", ")}</span>}
                      </dt>
                      <dd className="mt-1">
                        <Markdown className="text-[14.5px]">{t.definition}</Markdown>
                        {concept && (
                          <Link
                            to={concept.lessonId ? `/learn/${concept.lessonId}` : `/concept/${concept.id}`}
                            className="mt-1 inline-block text-[13px] text-accent underline underline-offset-2"
                          >
                            {concept.lessonId ? "Lesson" : "Concept"}: {concept.title} →
                          </Link>
                        )}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            </Card>
          </section>
        ))}
      </div>
    </div>
  );
}
