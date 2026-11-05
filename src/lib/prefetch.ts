// After the app becomes idle, fetch every screen and lesson chunk from the
// local server so that the whole app keeps working if the network (or the
// local server) disappears mid-session. Production builds only: in
// development it would force Vite to transform every module up front.
import { lessonLoaders } from "virtual:groundwork/lessons";
import { loadInterview, loadProjects, loadSearchDocs } from "../content/runtime";

export function prefetchAll(pages: (() => Promise<unknown>)[]): void {
  if (!import.meta.env.PROD) return;
  const idle =
    (window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number }).requestIdleCallback ??
    ((cb: () => void) => setTimeout(cb, 1500));
  idle(
    () => {
      const tasks: Promise<unknown>[] = [
        ...pages.map((load) => load()),
        ...Object.values(lessonLoaders).map((load) => load()),
        import("../components/CodeEditor"),
        import("../features/visualizations/PythonTracer"),
        loadSearchDocs(),
        loadProjects(),
        loadInterview(),
      ];
      void Promise.allSettled(tasks).then(() => {
        document.documentElement.dataset.prefetched = "true";
      });
    },
    { timeout: 4000 },
  );
}
