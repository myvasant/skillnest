// Browser access to compiled content (see scripts/vite-content-plugin.ts).
import index from "virtual:groundwork/index";
import { lessonLoaders } from "virtual:groundwork/lessons";
import type { SearchDoc } from "./build";
import type { InterviewQuestion, Lesson, Project } from "./schema";

export const curriculum = index;

const lessonCache = new Map<string, Promise<Lesson | null>>();

export function loadLesson(id: string): Promise<Lesson | null> {
  if (!lessonCache.has(id)) {
    const loader = lessonLoaders[id];
    lessonCache.set(id, loader ? loader() : Promise.resolve(null));
  }
  return lessonCache.get(id)!;
}

let projects: Promise<Record<string, Project>> | null = null;
export function loadProjects(): Promise<Record<string, Project>> {
  projects ??= import("virtual:groundwork/projects").then((m) => m.default);
  return projects;
}

let interview: Promise<Record<string, InterviewQuestion & { category: string }>> | null = null;
export function loadInterview(): Promise<Record<string, InterviewQuestion & { category: string }>> {
  interview ??= import("virtual:groundwork/interview").then((m) => m.default);
  return interview;
}

let search: Promise<SearchDoc[]> | null = null;
export function loadSearchDocs(): Promise<SearchDoc[]> {
  search ??= import("virtual:groundwork/search").then((m) => m.default);
  return search;
}

export const stageById = (id: string) => curriculum.stages.find((s) => s.id === id);
export const conceptTitle = (id: string) => curriculum.concepts[id]?.title ?? id;
