// Vite plugin that compiles content/*.yaml into virtual modules:
//   virtual:groundwork/index          curriculum index (graph, lessons meta, paths...)
//   virtual:groundwork/lessons        { [lessonId]: () => import(lesson module) }
//   virtual:groundwork/lesson/<id>    one lesson body (code-split per lesson)
//   virtual:groundwork/projects       project details
//   virtual:groundwork/interview      interview question bank
//   virtual:groundwork/search         search documents
// Content validation errors fail the build and show in the dev overlay.
import { resolve } from "node:path";
import type { Plugin, ViteDevServer } from "vite";
import { formatIssues, loadContent } from "../src/content/load.ts";
import type { CompiledContent } from "../src/content/build.ts";

const PREFIX = "virtual:groundwork/";
const RESOLVED = "\0" + PREFIX;

export function contentPlugin(): Plugin {
  const root = resolve(import.meta.dirname, "..");
  const contentDir = resolve(root, "content");
  let cache: CompiledContent | null = null;
  let server: ViteDevServer | null = null;
  let warned = false;

  const compiled = (): CompiledContent => {
    if (!cache) {
      cache = loadContent(root);
      const errors = cache.issues.filter((i) => i.severity === "error");
      const warnings = cache.issues.filter((i) => i.severity === "warning");
      if (warnings.length && !warned) {
        console.warn(`[content] ${warnings.length} warning(s):\n${formatIssues(warnings)}`);
        warned = true;
      }
      if (errors.length) {
        const message = `[content] ${errors.length} validation error(s):\n${formatIssues(errors)}`;
        if (!server) {
          // Production builds must never ship invalid content.
          cache = null;
          throw new Error(message);
        }
        // In development, keep serving everything that compiled and surface the
        // errors in an in-app banner, so one half-edited file doesn't take down the app.
        console.error(message);
      }
    }
    return cache;
  };

  const json = (value: unknown) => `export default JSON.parse(${JSON.stringify(JSON.stringify(value))});`;

  return {
    name: "groundwork-content",
    resolveId(id) {
      if (id.startsWith(PREFIX)) return "\0" + id;
      return null;
    },
    load(id) {
      if (!id.startsWith(RESOLVED)) return null;
      const name = id.slice(RESOLVED.length);
      const content = compiled();
      if (name === "index") return json(content.index);
      if (name === "issues") return json(server ? content.issues.filter((i) => i.severity === "error") : []);
      if (name === "search") return json(content.search);
      if (name === "projects") return json(content.projects);
      if (name === "interview") return json(content.interview);
      if (name === "lessons") {
        const entries = Object.keys(content.lessons).map(
          (lessonId) => `  ${JSON.stringify(lessonId)}: () => import(${JSON.stringify(`${PREFIX}lesson/${lessonId}`)}).then((m) => m.default),`,
        );
        return `export const lessonLoaders = {\n${entries.join("\n")}\n};`;
      }
      if (name.startsWith("lesson/")) {
        const lesson = content.lessons[name.slice("lesson/".length)];
        if (!lesson) throw new Error(`Unknown lesson module ${name}`);
        return json(lesson);
      }
      throw new Error(`Unknown virtual module ${id}`);
    },
    configureServer(devServer) {
      server = devServer;
      devServer.watcher.add(contentDir);
      const onChange = (file: string) => {
        if (!resolve(file).startsWith(contentDir)) return;
        cache = null;
        warned = false;
        for (const mod of devServer.moduleGraph.idToModuleMap.values()) {
          if (mod.id?.startsWith(RESOLVED)) devServer.moduleGraph.invalidateModule(mod);
        }
        devServer.ws.send({ type: "full-reload" });
      };
      devServer.watcher.on("change", onChange);
      devServer.watcher.on("add", onChange);
      devServer.watcher.on("unlink", onChange);
    },
    buildStart() {
      if (!server) compiled();
    },
  };
}
