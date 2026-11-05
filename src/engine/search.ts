// Small, dependency-free full-text search over curriculum documents.
// Scoring: title matches outweigh body matches; the last query word may be a
// prefix (search-as-you-type); every query word must match somewhere.
import type { SearchDoc } from "../content/build";

export interface SearchHit {
  doc: SearchDoc;
  score: number;
  snippet: string;
}

interface Indexed {
  doc: SearchDoc;
  titleTokens: string[];
  textTokens: Set<string>;
  textLower: string;
}

const KIND_BOOST: Record<SearchDoc["kind"], number> = {
  lesson: 1.35,
  concept: 1.2,
  glossary: 1.15,
  path: 1.1,
  stage: 1.05,
  project: 1.05,
  exercise: 1,
  interview: 0.95,
};

export function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^a-z0-9+#]+/)
    .filter(Boolean);
}

export class SearchIndex {
  private readonly entries: Indexed[];

  constructor(docs: SearchDoc[]) {
    this.entries = docs.map((doc) => ({
      doc,
      titleTokens: tokenize(doc.title),
      textTokens: new Set(tokenize(doc.text)),
      textLower: doc.text.toLowerCase(),
    }));
  }

  search(query: string, limit = 30): SearchHit[] {
    const terms = tokenize(query);
    if (!terms.length) return [];
    const phrase = query.trim().toLowerCase();
    const hits: SearchHit[] = [];
    for (const entry of this.entries) {
      let score = 0;
      let matchedAll = true;
      terms.forEach((term, i) => {
        const isLast = i === terms.length - 1;
        let s = 0;
        if (entry.titleTokens.includes(term)) s += 10;
        else if (entry.titleTokens.some((t) => t.startsWith(term) && (isLast || term.length >= 4))) s += 6;
        if (entry.textTokens.has(term)) s += 2;
        else if ((isLast || term.length >= 4) && [...entry.textTokens].some((t) => t.startsWith(term))) s += 1;
        if (s === 0) matchedAll = false;
        score += s;
      });
      if (!matchedAll) continue;
      const titleLower = entry.doc.title.toLowerCase();
      if (titleLower === phrase) score += 25;
      else if (titleLower.startsWith(phrase)) score += 8;
      else if (titleLower.includes(phrase)) score += 4;
      score *= KIND_BOOST[entry.doc.kind];
      hits.push({ doc: entry.doc, score, snippet: makeSnippet(entry.doc.text, entry.textLower, terms) });
    }
    return hits.sort((a, b) => b.score - a.score || a.doc.title.localeCompare(b.doc.title)).slice(0, limit);
  }
}

function makeSnippet(text: string, lower: string, terms: string[], width = 140): string {
  let at = -1;
  for (const term of terms) {
    at = lower.indexOf(term);
    if (at >= 0) break;
  }
  if (at < 0) return text.slice(0, width) + (text.length > width ? "…" : "");
  const start = Math.max(0, at - 40);
  const snippet = text.slice(start, start + width);
  return `${start > 0 ? "…" : ""}${snippet}${start + width < text.length ? "…" : ""}`;
}
