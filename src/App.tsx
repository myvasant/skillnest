import { lazy, Suspense, useEffect, type ComponentType, type ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import { AppShell } from "./features/layout/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Spinner } from "./components/ui";
import { prefetchAll } from "./lib/prefetch";

const loaders: (() => Promise<unknown>)[] = [];
const page = <T extends Record<string, unknown>>(loader: () => Promise<T>, name: keyof T) => {
  loaders.push(loader);
  return lazy(() => loader().then((m) => ({ default: m[name] as ComponentType })));
};

const DashboardPage = page(() => import("./features/dashboard/DashboardPage"), "DashboardPage");
const LessonPage = page(() => import("./features/lesson/LessonPage"), "LessonPage");
const CurriculumPage = page(() => import("./features/curriculum/CurriculumPage"), "CurriculumPage");
const ConceptPage = page(() => import("./features/curriculum/ConceptPage"), "ConceptPage");
const PathsPage = page(() => import("./features/paths/PathsPage"), "PathsPage");
const PathDetailPage = page(() => import("./features/paths/PathDetailPage"), "PathDetailPage");
const ReviewPage = page(() => import("./features/review/ReviewPage"), "ReviewPage");
const PlaygroundPage = page(() => import("./features/playground/PlaygroundPage"), "PlaygroundPage");
const ProjectsPage = page(() => import("./features/projects/ProjectsPage"), "ProjectsPage");
const ProjectPage = page(() => import("./features/projects/ProjectPage"), "ProjectPage");
const InterviewPage = page(() => import("./features/interview/InterviewPage"), "InterviewPage");
const GlossaryPage = page(() => import("./features/glossary/GlossaryPage"), "GlossaryPage");
const SettingsPage = page(() => import("./features/settings/SettingsPage"), "SettingsPage");
const VisualExplorerPage = page(() => import("./features/visualizations/VisualExplorerPage"), "VisualExplorerPage");
const NotFoundPage = page(() => import("./features/layout/NotFoundPage"), "NotFoundPage");

const fallback = (
  <div className="py-24 text-center">
    <Spinner label="Loading" />
  </div>
);

function Screen({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={fallback}>{children}</Suspense>
    </ErrorBoundary>
  );
}

export function App() {
  useEffect(() => prefetchAll(loaders), []);
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route
            index
            element={
              <Screen>
                <DashboardPage />
              </Screen>
            }
          />
          <Route
            path="learn/:lessonId"
            element={
              <Screen>
                <LessonPage />
              </Screen>
            }
          />
          <Route
            path="curriculum"
            element={
              <Screen>
                <CurriculumPage />
              </Screen>
            }
          />
          <Route
            path="concept/:conceptId"
            element={
              <Screen>
                <ConceptPage />
              </Screen>
            }
          />
          <Route
            path="paths"
            element={
              <Screen>
                <PathsPage />
              </Screen>
            }
          />
          <Route
            path="paths/:pathId"
            element={
              <Screen>
                <PathDetailPage />
              </Screen>
            }
          />
          <Route
            path="review"
            element={
              <Screen>
                <ReviewPage />
              </Screen>
            }
          />
          <Route
            path="playground"
            element={
              <Screen>
                <PlaygroundPage />
              </Screen>
            }
          />
          <Route
            path="projects"
            element={
              <Screen>
                <ProjectsPage />
              </Screen>
            }
          />
          <Route
            path="projects/:projectId"
            element={
              <Screen>
                <ProjectPage />
              </Screen>
            }
          />
          <Route
            path="interview"
            element={
              <Screen>
                <InterviewPage />
              </Screen>
            }
          />
          <Route
            path="glossary"
            element={
              <Screen>
                <GlossaryPage />
              </Screen>
            }
          />
          <Route
            path="visualize"
            element={
              <Screen>
                <VisualExplorerPage />
              </Screen>
            }
          />
          <Route
            path="settings"
            element={
              <Screen>
                <SettingsPage />
              </Screen>
            }
          />
          <Route
            path="*"
            element={
              <Screen>
                <NotFoundPage />
              </Screen>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
