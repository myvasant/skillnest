import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { Search, X } from "lucide-react";
import { loadSearchDocs } from "../../content/runtime";
import { SearchIndex, type SearchHit } from "../../engine/search";
import { Badge, Kbd, cn } from "../../components/ui";

const kindLabel: Record<string, string> = {
  lesson: "Lesson",
  concept: "Concept",
  glossary: "Glossary",
  exercise: "Exercise",
  project: "Project",
  interview: "Interview",
  path: "Path",
  stage: "Stage",
};

let indexPromise: Promise<SearchIndex> | null = null;
export const getSearchIndex = () => (indexPromise ??= loadSearchDocs().then((docs) => new SearchIndex(docs)));

export function SearchDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState<SearchIndex | null>(null);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      setTimeout(() => input.current?.focus(), 0);
      void getSearchIndex().then(setIndex);
    } else if (!open && d.open) d.close();
  }, [open]);

  const hits: SearchHit[] = useMemo(() => (index && query.trim() ? index.search(query, 40) : []), [index, query]);
  useEffect(() => setActive(0), [query]);

  const go = (hit: SearchHit) => {
    onClose();
    setQuery("");
    navigate(hit.doc.url);
  };

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && hits[active]) {
      e.preventDefault();
      go(hits[active]);
    }
  };

  useEffect(() => {
    document.getElementById(`search-hit-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && onClose()}
      aria-label="Search"
      className="m-auto mt-[10vh] w-[min(680px,calc(100vw-2rem))] rounded-2xl border border-border bg-surface p-0 text-text shadow-pop backdrop:bg-black/40 backdrop:backdrop-blur-[2px]"
    >
      <div className="flex items-center gap-3 border-b border-border px-4">
        <Search className="size-5 text-muted" aria-hidden />
        <input
          ref={input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKey}
          placeholder="Search lessons, concepts, glossary, exercises, projects, interview questions…"
          className="h-14 flex-1 bg-transparent text-[15px] outline-none placeholder:text-faint"
          role="combobox"
          aria-expanded={hits.length > 0}
          aria-controls="search-results"
          aria-activedescendant={hits.length ? `search-hit-${active}` : undefined}
          aria-label="Search query"
        />
        <button onClick={onClose} className="rounded p-1 text-muted hover:text-text" aria-label="Close search">
          <X className="size-4" />
        </button>
      </div>
      <div className="scrollbar-thin max-h-[60vh] overflow-y-auto p-2">
        {!index && <p className="p-4 text-sm text-muted">Loading search index…</p>}
        {index && !query.trim() && (
          <p className="p-4 text-sm text-muted">Try “variables”, “NameError”, “float”, “recursion” or “RAG”. Search runs entirely on your device.</p>
        )}
        {index && query.trim() && hits.length === 0 && <p className="p-4 text-sm text-muted">No matches for “{query}”.</p>}
        <ul id="search-results" role="listbox" aria-label="Search results">
          {hits.map((hit, i) => (
            <li
              key={hit.doc.id}
              id={`search-hit-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onClick={() => go(hit)}
              className={cn("cursor-pointer rounded-lg px-3 py-2.5", i === active ? "bg-accent-soft" : "hover:bg-surface-2")}
            >
              <div className="flex items-center gap-2">
                <Badge tone={hit.doc.kind === "lesson" ? "accent" : hit.doc.kind === "concept" ? "info" : "neutral"}>{kindLabel[hit.doc.kind]}</Badge>
                <span className="truncate font-medium">{hit.doc.title}</span>
                {hit.doc.context && <span className="ml-auto shrink-0 text-[12px] text-faint">{hit.doc.context}</span>}
              </div>
              <p className="mt-0.5 line-clamp-2 text-[13px] text-muted">{hit.snippet}</p>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex items-center gap-3 border-t border-border px-4 py-2 text-[12px] text-faint">
        <span>
          <Kbd>↑</Kbd> <Kbd>↓</Kbd> to move
        </span>
        <span>
          <Kbd>Enter</Kbd> to open
        </span>
        <span>
          <Kbd>Esc</Kbd> to close
        </span>
      </div>
    </dialog>
  );
}
