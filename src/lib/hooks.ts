import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { curriculum } from "../content/runtime";
import { allMastery, type ConceptMastery } from "../engine/mastery";
import { recommend, type RecommendationSet } from "../engine/recommend";
import { python, type RuntimeStatus } from "../python/client";
import { useProgress } from "../storage/store";

export type AsyncState<T> = { status: "loading" } | { status: "ready"; value: T } | { status: "error"; error: Error };

export function useAsync<T>(factory: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });
    factory().then(
      (value) => alive && setState({ status: "ready", value }),
      (error: unknown) => alive && setState({ status: "error", error: error instanceof Error ? error : new Error(String(error)) }),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

/** Mastery for every concept, recomputed when progress changes. */
export function useMastery(): Record<string, ConceptMastery> {
  const progress = useProgress();
  return useMemo(() => allMastery(curriculum, progress, new Date()), [progress]);
}

export function useRecommendations(): RecommendationSet {
  const progress = useProgress();
  return useMemo(() => recommend(curriculum, progress, new Date()), [progress]);
}

export function usePythonStatus(): RuntimeStatus {
  return useSyncExternalStore(python.subscribe, python.getStatus, python.getStatus);
}

export function useOnline(): boolean {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener("online", cb);
      window.addEventListener("offline", cb);
      return () => {
        window.removeEventListener("online", cb);
        window.removeEventListener("offline", cb);
      };
    },
    () => navigator.onLine,
    () => true,
  );
}

export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title ? `${title} · Groundwork` : "Groundwork";
  }, [title]);
}

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", cb);
      return () => mql.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
