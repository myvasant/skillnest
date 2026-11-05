declare module "virtual:groundwork/index" {
  const index: import("./content/build").CurriculumIndex;
  export default index;
}

declare module "virtual:groundwork/issues" {
  /** Content validation errors (development server only; always empty in builds). */
  const issues: import("./content/build").ValidationIssue[];
  export default issues;
}

declare module "virtual:groundwork/lessons" {
  export const lessonLoaders: Record<string, () => Promise<import("./content/schema").Lesson>>;
}

declare module "virtual:groundwork/projects" {
  const projects: Record<string, import("./content/schema").Project>;
  export default projects;
}

declare module "virtual:groundwork/interview" {
  const interview: Record<string, import("./content/schema").InterviewQuestion & { category: string }>;
  export default interview;
}

declare module "virtual:groundwork/search" {
  const docs: import("./content/build").SearchDoc[];
  export default docs;
}

declare module "*.py?raw" {
  const source: string;
  export default source;
}
