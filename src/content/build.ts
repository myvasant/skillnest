// Content compiler: validates raw YAML data and derives the curriculum index
// (knowledge graph, learning paths, item index, search documents).
// Pure and isomorphic so it can be unit-tested without the file system.
import type { z } from "zod";
import {
  GlossarySchema,
  InterviewFileSchema,
  LessonSchema,
  PathsFileSchema,
  ProjectSchema,
  StageSchema,
  type Concept,
  type GlossaryTerm,
  type InterviewQuestion,
  type Item,
  type LearningPath,
  type Lesson,
  type Level,
  type Priority,
  type Project,
  type Skill,
  type Source,
  type Stage,
} from "./schema.ts";
import { isVisualizationId, visualizationSchemas } from "./visualizationSchemas.ts";

export interface RawFile {
  file: string;
  data: unknown;
}

export interface LinkStatus {
  ok: boolean;
  verdict: "ok" | "redirect" | "blocked" | "broken" | "error";
  status: number | null;
  checkedAt: string;
}

export interface RawContent {
  /** Output of scripts/check-links.ts, if it has been run. */
  linkReport?: Record<string, LinkStatus>;
  stages: RawFile[];
  lessons: RawFile[];
  glossary: RawFile[];
  paths: RawFile | null;
  projects: RawFile[];
  interview: RawFile[];
}

export interface ValidationIssue {
  severity: "error" | "warning";
  file: string;
  path: string;
  message: string;
}

export interface ConceptNode extends Concept {
  stage: string;
  requiredBy: string[];
  extendedBy: string[];
  lessonId: string | null;
  projectIds: string[];
  interviewIds: string[];
  itemIds: string[];
  glossaryIds: string[];
  /** Length of the longest prerequisite chain leading to this concept. */
  depth: number;
}

export interface StageMeta {
  id: string;
  order: number;
  title: string;
  shortTitle: string;
  summary: string;
  why: string;
  modules: { id: string; title: string; summary: string; conceptIds: string[] }[];
  conceptIds: string[];
}

export interface LessonMeta {
  id: string;
  concept: string;
  title: string;
  subtitle?: string;
  summary: string;
  estimatedMinutes: number;
  stage: string;
  module: string;
  level: Level;
  sections: { id: string; title: string; depth: "core" | "deep" }[];
  itemCount: number;
  exerciseCount: number;
  masteryItemIds: string[];
  passThreshold: number;
  reviewedOn: string;
}

export interface ItemMeta {
  gid: string;
  lessonId: string;
  itemId: string;
  type: Item["type"];
  skill: Skill;
  difficulty: number;
  concepts: string[];
  mastery: boolean;
}

export interface PathMeta extends LearningPath {
  conceptIds: string[];
}

export interface ProjectMeta {
  id: string;
  title: string;
  track: Project["track"];
  level: Level;
  estimatedHours: number;
  summary: string;
  concepts: string[];
  environment: Project["environment"];
  milestoneIds: string[];
}

export interface InterviewCategoryMeta {
  id: string;
  title: string;
  summary: string;
  questionIds: string[];
}

export interface SearchDoc {
  id: string;
  kind: "concept" | "lesson" | "glossary" | "exercise" | "project" | "interview" | "path" | "stage";
  title: string;
  text: string;
  url: string;
  context?: string;
}

export interface CurriculumIndex {
  stages: StageMeta[];
  concepts: Record<string, ConceptNode>;
  /** Every concept, prerequisites before dependents, stable by stage and file order. */
  conceptOrder: string[];
  lessons: Record<string, LessonMeta>;
  items: Record<string, ItemMeta>;
  glossary: GlossaryTerm[];
  paths: PathMeta[];
  defaultPath: string;
  projects: ProjectMeta[];
  interviewCategories: InterviewCategoryMeta[];
  /** Link-check results for every source URL that has been checked (see scripts/check-links.ts). */
  links: Record<string, Pick<LinkStatus, "ok" | "verdict" | "checkedAt">>;
  stats: {
    stages: number;
    modules: number;
    concepts: number;
    lessons: number;
    items: number;
    projects: number;
    interviewQuestions: number;
    glossaryTerms: number;
    byPriority: Record<Priority, number>;
  };
}

export interface CompiledContent {
  index: CurriculumIndex;
  lessons: Record<string, Lesson>;
  projects: Record<string, Project>;
  interview: Record<string, InterviewQuestion & { category: string }>;
  search: SearchDoc[];
  issues: ValidationIssue[];
}

export const itemGid = (lessonId: string, itemId: string) => `${lessonId}/${itemId}`;

const INTERNAL_LINK = /\]\((concept|lesson|glossary|project|interview):([^)\s]+)\)/g;

function parseWith<T extends z.ZodType>(schema: T, raw: RawFile, issues: ValidationIssue[]): z.infer<T> | null {
  const result = schema.safeParse(raw.data);
  if (result.success) return result.data;
  for (const issue of result.error.issues) {
    issues.push({ severity: "error", file: raw.file, path: issue.path.join("."), message: issue.message });
  }
  return null;
}

/** Collect every markdown-bearing string in a value, with its JSON path. */
function collectStrings(value: unknown, path: string, out: { path: string; text: string }[]): void {
  if (typeof value === "string") {
    if (value.includes("](")) out.push({ path, text: value });
  } else if (Array.isArray(value)) {
    value.forEach((v, i) => collectStrings(v, `${path}.${i}`, out));
  } else if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) collectStrings(v, path ? `${path}.${k}` : k, out);
  }
}

function stripMarkdown(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[#>*_|~-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function compileContent(raw: RawContent): CompiledContent {
  const issues: ValidationIssue[] = [];
  const error = (file: string, path: string, message: string) => issues.push({ severity: "error", file, path, message });
  const warn = (file: string, path: string, message: string) => issues.push({ severity: "warning", file, path, message });

  // ---- Stages and concepts ------------------------------------------------
  const stages: { stage: Stage; file: string }[] = [];
  for (const rawStage of raw.stages) {
    const stage = parseWith(StageSchema, rawStage, issues);
    if (stage) stages.push({ stage, file: rawStage.file });
  }
  stages.sort((a, b) => a.stage.order - b.stage.order);

  const concepts: Record<string, ConceptNode> = {};
  const conceptFile: Record<string, string> = {};
  const fileOrder: string[] = [];
  const seenStage = new Set<string>();
  const seenOrder = new Set<number>();
  for (const { stage, file } of stages) {
    if (seenStage.has(stage.id)) error(file, "id", `duplicate stage id "${stage.id}"`);
    if (seenOrder.has(stage.order)) error(file, "order", `duplicate stage order ${stage.order}`);
    seenStage.add(stage.id);
    seenOrder.add(stage.order);
    const moduleIds = new Set<string>();
    for (const m of stage.modules) {
      if (moduleIds.has(m.id)) error(file, `modules.${m.id}`, `duplicate module id "${m.id}"`);
      moduleIds.add(m.id);
    }
    stage.concepts.forEach((c, i) => {
      if (concepts[c.id]) {
        error(file, `concepts.${i}.id`, `duplicate concept id "${c.id}" (also in ${conceptFile[c.id]})`);
        return;
      }
      if (!moduleIds.has(c.module)) error(file, `concepts.${i}.module`, `concept "${c.id}" uses unknown module "${c.module}"`);
      concepts[c.id] = {
        ...c,
        stage: stage.id,
        requiredBy: [],
        extendedBy: [],
        lessonId: null,
        projectIds: [],
        interviewIds: [],
        itemIds: [],
        glossaryIds: [],
        depth: 0,
      };
      conceptFile[c.id] = file;
      fileOrder.push(c.id);
    });
  }

  for (const id of fileOrder) {
    const c = concepts[id]!;
    const file = conceptFile[id]!;
    const relations = ["requires", "extends", "contrastsWith", "confusedWith"] as const;
    for (const rel of relations) {
      const seen = new Set<string>();
      for (const target of c[rel]) {
        if (target === id) error(file, `${id}.${rel}`, `concept "${id}" cannot reference itself in ${rel}`);
        else if (!concepts[target]) error(file, `${id}.${rel}`, `concept "${id}" ${rel} unknown concept "${target}"`);
        if (seen.has(target)) warn(file, `${id}.${rel}`, `"${target}" is listed twice in ${rel}`);
        seen.add(target);
      }
    }
  }

  // Symmetric relations and reverse edges.
  for (const id of fileOrder) {
    const c = concepts[id]!;
    c.requires = c.requires.filter((r) => concepts[r] && r !== id);
    c.extends = c.extends.filter((r) => concepts[r] && r !== id);
    for (const r of c.requires) concepts[r]!.requiredBy.push(id);
    for (const r of c.extends) concepts[r]!.extendedBy.push(id);
    for (const rel of ["contrastsWith", "confusedWith"] as const) {
      c[rel] = c[rel].filter((r) => concepts[r] && r !== id);
      for (const r of c[rel]) {
        const other = concepts[r]!;
        if (!other[rel].includes(id)) other[rel] = [...other[rel], id];
      }
    }
  }

  // Topological order (Kahn), tie-broken by stage then file order; detect cycles.
  const position = new Map(fileOrder.map((id, i) => [id, i]));
  const indegree = new Map(fileOrder.map((id) => [id, concepts[id]!.requires.length]));
  const ready = fileOrder.filter((id) => indegree.get(id) === 0);
  const conceptOrder: string[] = [];
  while (ready.length) {
    ready.sort((a, b) => position.get(a)! - position.get(b)!);
    const id = ready.shift()!;
    conceptOrder.push(id);
    for (const dep of concepts[id]!.requiredBy) {
      const left = indegree.get(dep)! - 1;
      indegree.set(dep, left);
      if (left === 0) ready.push(dep);
    }
  }
  if (conceptOrder.length !== fileOrder.length) {
    const stuck = fileOrder.filter((id) => !conceptOrder.includes(id));
    error("content/stages", "requires", `prerequisite cycle involving: ${stuck.slice(0, 12).join(", ")}`);
    conceptOrder.push(...stuck);
  } else {
    for (const id of conceptOrder) {
      const c = concepts[id]!;
      c.depth = c.requires.reduce((max, r) => Math.max(max, concepts[r]!.depth + 1), 0);
    }
  }

  // ---- Lessons and items --------------------------------------------------
  const lessons: Record<string, Lesson> = {};
  const lessonMeta: Record<string, LessonMeta> = {};
  const items: Record<string, ItemMeta> = {};
  const lessonFiles: Record<string, string> = {};
  for (const rawLesson of raw.lessons) {
    const lesson = parseWith(LessonSchema, rawLesson, issues);
    if (!lesson) continue;
    const file = rawLesson.file;
    if (lessons[lesson.id]) {
      error(file, "id", `duplicate lesson id "${lesson.id}" (also in ${lessonFiles[lesson.id]})`);
      continue;
    }
    const concept = concepts[lesson.concept];
    if (!concept) {
      error(file, "concept", `lesson "${lesson.id}" teaches unknown concept "${lesson.concept}"`);
      continue;
    }
    if (concept.lessonId) {
      error(file, "concept", `concept "${lesson.concept}" already has lesson "${concept.lessonId}"`);
      continue;
    }
    concept.lessonId = lesson.id;
    lessons[lesson.id] = lesson;
    lessonFiles[lesson.id] = file;

    const itemIds = new Set<string>();
    lesson.items.forEach((item, i) => {
      if (itemIds.has(item.id)) error(file, `items.${i}.id`, `duplicate item id "${item.id}"`);
      itemIds.add(item.id);
      for (const c of item.concepts ?? []) {
        if (!concepts[c]) error(file, `items.${i}.concepts`, `item "${item.id}" references unknown concept "${c}"`);
      }
      if (item.type === "mcq") {
        const correct = item.options.filter((o) => o.correct).length;
        if (correct === 0) error(file, `items.${i}.options`, `mcq "${item.id}" has no correct option`);
        const optionIds = new Set(item.options.map((o) => o.id));
        if (optionIds.size !== item.options.length) error(file, `items.${i}.options`, `mcq "${item.id}" has duplicate option ids`);
      }
      if (item.type === "code" || item.type === "debug") {
        if (item.starterCode.trim() === item.solution.trim()) error(file, `items.${i}.starterCode`, `"${item.id}": starter code is identical to the solution`);
      }
      if (item.type === "parsons" && item.solution.split("\n").filter((l) => l.trim()).length < 3) {
        error(file, `items.${i}.solution`, `parsons "${item.id}" needs at least 3 lines`);
      }
    });

    const referenced = new Set<string>();
    const sectionIds = new Set<string>();
    const codeIds = new Set<string>();
    lesson.sections.forEach((section, si) => {
      if (sectionIds.has(section.id)) error(file, `sections.${si}.id`, `duplicate section id "${section.id}"`);
      sectionIds.add(section.id);
      section.blocks.forEach((block, bi) => {
        const at = `sections.${si}.blocks.${bi}`;
        if (block.type === "item") {
          if (!itemIds.has(block.ref)) error(file, at, `block references unknown item "${block.ref}"`);
          referenced.add(block.ref);
        }
        if (block.type === "code") {
          if (block.id) {
            if (codeIds.has(block.id)) error(file, at, `duplicate code block id "${block.id}"`);
            codeIds.add(block.id);
          }
          if (block.runnable && block.language !== "python") error(file, at, "only python code blocks can be runnable");
          if (
            block.language === "python" &&
            block.status !== "illustrative" &&
            block.status !== "pseudocode" &&
            block.expectedOutput === undefined &&
            !block.expectError
          ) {
            warn(file, at, "python example has no expectedOutput, so it is only syntax-checked; add expectedOutput or mark status: illustrative");
          }
          for (const a of block.annotations) {
            if (a.line > block.code.split("\n").length) error(file, at, `annotation for line ${a.line} is past the end of the code`);
          }
        }
        if (block.type === "visualization") {
          if (!isVisualizationId(block.component)) {
            error(file, at, `unknown visualization "${block.component}"`);
          } else {
            const parsed = visualizationSchemas[block.component].safeParse(block.props);
            if (!parsed.success) {
              for (const issue of parsed.error.issues) error(file, `${at}.props.${issue.path.join(".")}`, issue.message);
            }
          }
        }
      });
    });

    const masteryIds = lesson.masteryCheck?.items ?? [];
    for (const m of masteryIds) {
      if (!itemIds.has(m)) error(file, "masteryCheck.items", `mastery check references unknown item "${m}"`);
      referenced.add(m);
    }
    if (lesson.masteryCheck) {
      const kinds = new Set(masteryIds.map((m) => lesson.items.find((i) => i.id === m)?.type));
      if (!kinds.has("code") && !kinds.has("debug")) {
        warn(file, "masteryCheck", "mastery check has no code/debug item, so it cannot show independent implementation");
      }
    } else {
      warn(file, "masteryCheck", "lesson has no mastery check");
    }
    for (const item of lesson.items) {
      if (!referenced.has(item.id)) warn(file, "items", `item "${item.id}" is not used in any section or the mastery check`);
    }

    for (const item of lesson.items) {
      const gid = itemGid(lesson.id, item.id);
      const itemConcepts = item.concepts && item.concepts.length ? item.concepts : [lesson.concept];
      items[gid] = {
        gid,
        lessonId: lesson.id,
        itemId: item.id,
        type: item.type,
        skill: item.skill,
        difficulty: item.difficulty,
        concepts: itemConcepts,
        mastery: masteryIds.includes(item.id),
      };
      for (const c of itemConcepts) concepts[c]?.itemIds.push(gid);
    }

    lessonMeta[lesson.id] = {
      id: lesson.id,
      concept: lesson.concept,
      title: lesson.title,
      subtitle: lesson.subtitle,
      summary: lesson.summary,
      estimatedMinutes: lesson.estimatedMinutes,
      stage: concept.stage,
      module: concept.module,
      level: concept.level,
      sections: lesson.sections.map((s) => ({ id: s.id, title: s.title, depth: s.depth })),
      itemCount: lesson.items.length,
      exerciseCount: lesson.items.filter((i) => i.type === "code" || i.type === "debug").length,
      masteryItemIds: masteryIds.map((m) => itemGid(lesson.id, m)),
      passThreshold: lesson.masteryCheck?.passThreshold ?? 0.8,
      reviewedOn: lesson.reviewedOn,
    };
  }

  // ---- Glossary (may be split across several files) -------------------------
  const glossaryTerms: GlossaryTerm[] = [];
  const glossaryIdSet = new Set<string>();
  const glossaryNames = new Set<string>();
  for (const rawGlossary of raw.glossary) {
    const parsed = parseWith(GlossarySchema, rawGlossary, issues);
    if (!parsed) continue;
    parsed.terms.forEach((t, i) => {
      const key = t.term.toLowerCase();
      if (glossaryIdSet.has(t.id)) {
        error(rawGlossary.file, `terms.${i}.id`, `duplicate glossary id "${t.id}"`);
        return;
      }
      if (glossaryNames.has(key)) {
        error(rawGlossary.file, `terms.${i}.term`, `duplicate glossary term "${t.term}"`);
        return;
      }
      glossaryIdSet.add(t.id);
      glossaryNames.add(key);
      if (t.concept) {
        if (!concepts[t.concept]) error(rawGlossary.file, `terms.${i}.concept`, `term "${t.id}" links unknown concept "${t.concept}"`);
        else concepts[t.concept]!.glossaryIds.push(t.id);
      }
      glossaryTerms.push(t);
    });
  }
  const glossary = glossaryTerms.sort((a, b) => a.term.localeCompare(b.term));

  // ---- Learning paths -------------------------------------------------------
  let paths: PathMeta[] = [];
  let defaultPath = "";
  if (raw.paths) {
    const parsed = parseWith(PathsFileSchema, raw.paths, issues);
    if (parsed) {
      defaultPath = parsed.defaultPath;
      if (!parsed.paths.some((p) => p.id === parsed.defaultPath)) error(raw.paths.file, "defaultPath", `unknown default path "${parsed.defaultPath}"`);
      paths = parsed.paths.map((p, i) => {
        for (const t of p.targets) if (!concepts[t]) error(raw.paths!.file, `paths.${i}.targets`, `path "${p.id}" targets unknown concept "${t}"`);
        return {
          ...p,
          conceptIds: resolvePath(
            p.targets.filter((t) => concepts[t]),
            concepts,
            conceptOrder,
          ),
        };
      });
    }
  }

  // ---- Projects ---------------------------------------------------------------
  const projects: Record<string, Project> = {};
  for (const rawProject of raw.projects) {
    const project = parseWith(ProjectSchema, rawProject, issues);
    if (!project) continue;
    if (projects[project.id]) {
      error(rawProject.file, "id", `duplicate project id "${project.id}"`);
      continue;
    }
    projects[project.id] = project;
    for (const c of project.concepts) {
      if (!concepts[c]) error(rawProject.file, "concepts", `project "${project.id}" references unknown concept "${c}"`);
      else concepts[c]!.projectIds.push(project.id);
    }
    const ms = new Set<string>();
    for (const m of project.milestones) {
      if (ms.has(m.id)) error(rawProject.file, "milestones", `duplicate milestone id "${m.id}"`);
      ms.add(m.id);
    }
    if (project.environment === "browser" && !project.milestones.some((m) => m.tests.length)) {
      error(rawProject.file, "milestones", `browser project "${project.id}" needs in-browser tests on at least one milestone`);
    }
  }

  // ---- Interview questions ----------------------------------------------------
  const interview: Record<string, InterviewQuestion & { category: string }> = {};
  const interviewCategories: InterviewCategoryMeta[] = [];
  for (const rawFile of raw.interview) {
    const parsed = parseWith(InterviewFileSchema, rawFile, issues);
    if (!parsed) continue;
    // Several files may contribute to one category; the first file's title and summary are used.
    let category = interviewCategories.find((c) => c.id === parsed.category.id);
    if (!category) {
      category = { ...parsed.category, questionIds: [] };
      interviewCategories.push(category);
    }
    const questionIds = category.questionIds;
    parsed.questions.forEach((q, i) => {
      if (interview[q.id]) {
        error(rawFile.file, `questions.${i}.id`, `duplicate interview question id "${q.id}"`);
        return;
      }
      interview[q.id] = { ...q, category: parsed.category.id };
      questionIds.push(q.id);
      for (const c of q.concepts) {
        if (!concepts[c]) error(rawFile.file, `questions.${i}.concepts`, `question "${q.id}" references unknown concept "${c}"`);
        else concepts[c]!.interviewIds.push(q.id);
      }
    });
  }

  // ---- Internal markdown links ------------------------------------------------
  const glossaryIds = new Set(glossary.map((g) => g.id));
  const exists: Record<string, (id: string) => boolean> = {
    concept: (id) => Boolean(concepts[id]),
    lesson: (id) => Boolean(lessons[id]),
    glossary: (id) => glossaryIds.has(id),
    project: (id) => Boolean(projects[id]),
    interview: (id) => Boolean(interview[id]),
  };
  const checkLinks = (file: string, value: unknown) => {
    const strings: { path: string; text: string }[] = [];
    collectStrings(value, "", strings);
    for (const { path, text } of strings) {
      for (const match of text.matchAll(INTERNAL_LINK)) {
        const [, kind, id] = match;
        if (!exists[kind!]!(id!)) error(file, path, `broken internal link ${kind}:${id}`);
      }
    }
  };
  for (const r of [...raw.stages, ...raw.lessons, ...raw.projects, ...raw.interview, ...raw.glossary]) checkLinks(r.file, r.data);
  if (raw.paths) checkLinks(raw.paths.file, raw.paths.data);

  // ---- Assemble -------------------------------------------------------------
  const stageMeta: StageMeta[] = stages.map(({ stage }) => ({
    id: stage.id,
    order: stage.order,
    title: stage.title,
    shortTitle: stage.shortTitle,
    summary: stage.summary,
    why: stage.why,
    modules: stage.modules.map((m) => ({ ...m, conceptIds: stage.concepts.filter((c) => c.module === m.id).map((c) => c.id) })),
    conceptIds: stage.concepts.map((c) => c.id),
  }));

  const byPriority = { essential: 0, supporting: 0, advanced: 0, optional: 0, "technology-specific": 0 } as Record<Priority, number>;
  for (const c of Object.values(concepts)) byPriority[c.priority] += 1;

  const projectMeta: ProjectMeta[] = Object.values(projects).map((p) => ({
    id: p.id,
    title: p.title,
    track: p.track,
    level: p.level,
    estimatedHours: p.estimatedHours,
    summary: p.summary,
    concepts: p.concepts,
    environment: p.environment,
    milestoneIds: p.milestones.map((m) => m.id),
  }));

  // Only keep link results for URLs used as sources (keeps the index small).
  const links: CurriculumIndex["links"] = {};
  if (raw.linkReport) {
    const sourceUrls = new Set<string>();
    for (const c of Object.values(concepts)) for (const s of c.sources) sourceUrls.add(s.url);
    for (const l of Object.values(lessons)) for (const s of l.sources) sourceUrls.add(s.url);
    for (const url of sourceUrls) {
      const r = raw.linkReport[url];
      if (r) links[url] = { ok: r.ok, verdict: r.verdict, checkedAt: r.checkedAt };
    }
  }

  const index: CurriculumIndex = {
    stages: stageMeta,
    links,
    concepts,
    conceptOrder,
    lessons: lessonMeta,
    items,
    glossary,
    paths,
    defaultPath,
    projects: projectMeta,
    interviewCategories,
    stats: {
      stages: stageMeta.length,
      modules: stageMeta.reduce((n, s) => n + s.modules.length, 0),
      concepts: fileOrder.length,
      lessons: Object.keys(lessons).length,
      items: Object.keys(items).length,
      projects: projectMeta.length,
      interviewQuestions: Object.keys(interview).length,
      glossaryTerms: glossary.length,
      byPriority,
    },
  };

  return { index, lessons, projects, interview, search: buildSearchDocs(index, lessons, projects, interview), issues };
}

/** All prerequisites of the targets (transitively) plus the targets, in curriculum order. */
export function resolvePath(targets: string[], concepts: Record<string, { requires: string[] }>, order: string[]): string[] {
  const needed = new Set<string>();
  const visit = (id: string) => {
    if (needed.has(id) || !concepts[id]) return;
    needed.add(id);
    for (const r of concepts[id]!.requires) visit(r);
  };
  targets.forEach(visit);
  return order.filter((id) => needed.has(id));
}

function buildSearchDocs(
  index: CurriculumIndex,
  lessons: Record<string, Lesson>,
  projects: Record<string, Project>,
  interview: Record<string, InterviewQuestion & { category: string }>,
): SearchDoc[] {
  const docs: SearchDoc[] = [];
  for (const s of index.stages) {
    docs.push({ id: `stage:${s.id}`, kind: "stage", title: s.title, text: `${s.summary} ${s.why}`, url: `/curriculum?stage=${s.id}` });
  }
  for (const c of Object.values(index.concepts)) {
    const stage = index.stages.find((s) => s.id === c.stage);
    docs.push({
      id: `concept:${c.id}`,
      kind: "concept",
      title: c.title,
      text: stripMarkdown([c.summary, c.why ?? "", ...c.keyIdeas, ...c.misconceptions, ...c.tools].join(" ")),
      url: `/concept/${c.id}`,
      context: stage?.shortTitle,
    });
  }
  for (const lesson of Object.values(lessons)) {
    const body: string[] = [lesson.summary, ...lesson.objectives];
    for (const section of lesson.sections) {
      body.push(section.title);
      for (const block of section.blocks) {
        if (block.type === "markdown" || block.type === "callout") body.push(block.body);
        if (block.type === "code") body.push(block.caption ?? "", block.code);
      }
    }
    docs.push({
      id: `lesson:${lesson.id}`,
      kind: "lesson",
      title: lesson.title,
      text: stripMarkdown(body.join(" ")),
      url: `/learn/${lesson.id}`,
      context: "Lesson",
    });
    for (const item of lesson.items) {
      if (item.type === "code" || item.type === "debug" || item.type === "parsons") {
        docs.push({
          id: `exercise:${lesson.id}/${item.id}`,
          kind: "exercise",
          title: stripMarkdown(item.prompt).slice(0, 90),
          text: stripMarkdown(item.prompt),
          url: `/learn/${lesson.id}#item-${item.id}`,
          context: lesson.title,
        });
      }
    }
  }
  for (const g of index.glossary) {
    docs.push({
      id: `glossary:${g.id}`,
      kind: "glossary",
      title: g.term,
      text: stripMarkdown(`${g.aliases.join(" ")} ${g.definition}`),
      url: `/glossary#${g.id}`,
      context: "Glossary",
    });
  }
  for (const p of Object.values(projects)) {
    docs.push({
      id: `project:${p.id}`,
      kind: "project",
      title: p.title,
      text: stripMarkdown(`${p.summary} ${p.problem}`),
      url: `/projects/${p.id}`,
      context: "Project",
    });
  }
  for (const q of Object.values(interview)) {
    docs.push({
      id: `interview:${q.id}`,
      kind: "interview",
      title: stripMarkdown(q.question).slice(0, 110),
      text: stripMarkdown(`${q.question} ${q.keyPoints.join(" ")}`),
      url: `/interview?q=${q.id}`,
      context: "Interview",
    });
  }
  for (const p of index.paths) {
    docs.push({
      id: `path:${p.id}`,
      kind: "path",
      title: p.title,
      text: `${p.role} ${p.summary} ${p.outcomes.join(" ")}`,
      url: `/paths/${p.id}`,
      context: "Learning path",
    });
  }
  return docs;
}

export type { Source };
