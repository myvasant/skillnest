import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import {
  BookA,
  Hammer,
  LayoutDashboard,
  Map,
  Menu,
  MessagesSquare,
  Moon,
  Repeat,
  Route,
  Search,
  Settings,
  Shapes,
  Sun,
  TerminalSquare,
  WifiOff,
  X,
} from "lucide-react";
import { Kbd, cn } from "../../components/ui";
import { useMastery, useMediaQuery, useOnline, usePythonStatus } from "../../lib/hooks";
import { updateSettings } from "../../storage/actions";
import { progressStore, useProgressSelector } from "../../storage/store";
import { SearchDialog } from "./SearchDialog";
import contentIssues from "virtual:groundwork/issues";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/curriculum", label: "Curriculum", icon: Map },
  { to: "/paths", label: "Learning paths", icon: Route },
  { to: "/review", label: "Review", icon: Repeat },
  { to: "/playground", label: "Playground", icon: TerminalSquare },
  { to: "/visualize", label: "Visual explorer", icon: Shapes },
  { to: "/projects", label: "Projects", icon: Hammer },
  { to: "/interview", label: "Interview prep", icon: MessagesSquare },
  { to: "/glossary", label: "Glossary", icon: BookA },
  { to: "/settings", label: "Settings", icon: Settings },
];

function ContentIssuesBanner() {
  const [open, setOpen] = useState(false);
  if (!contentIssues.length) return null;
  return (
    <div role="alert" className="border-b border-danger/40 bg-danger-soft px-4 py-2 text-[13px] text-danger md:px-8">
      <button className="font-semibold underline underline-offset-2" onClick={() => setOpen((o) => !o)}>
        Development: {contentIssues.length} content validation error{contentIssues.length === 1 ? "" : "s"} — affected files were skipped.
      </button>
      {open && (
        <ul className="mt-1 max-h-48 list-disc overflow-auto pl-5 font-mono text-[12px]">
          {contentIssues.map((i, n) => (
            <li key={n}>
              {i.file}
              {i.path ? ` @ ${i.path}` : ""}: {i.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ThemeController() {
  const theme = useProgressSelector((p) => p.settings.theme);
  const motion = useProgressSelector((p) => p.settings.motion);
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");
  useEffect(() => {
    const dark = theme === "dark" || (theme === "system" && prefersDark);
    document.documentElement.classList.toggle("dark", dark);
  }, [theme, prefersDark]);
  useEffect(() => {
    document.documentElement.classList.toggle("reduce-motion", motion === "reduce");
  }, [motion]);
  return null;
}

function RuntimeIndicator() {
  const status = usePythonStatus();
  const online = useOnline();
  const label: Record<string, string> = {
    idle: "Python idle",
    loading: "Starting Python…",
    ready: "Python ready",
    busy: "Running…",
    error: "Python unavailable",
  };
  const dot: Record<string, string> = {
    idle: "bg-faint",
    loading: "bg-warning animate-pulse",
    ready: "bg-success",
    busy: "bg-info animate-pulse",
    error: "bg-danger",
  };
  return (
    <div className="flex items-center gap-3 text-[12px] text-muted">
      {!online && (
        <span
          className="inline-flex items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-warning"
          title="Offline: lessons, Python (standard library) and progress keep working. Loading extra packages such as numpy needs internet."
        >
          <WifiOff className="size-3.5" aria-hidden /> Offline
        </span>
      )}
      <span className="hidden items-center gap-1.5 sm:inline-flex" role="status" aria-live="polite">
        <span className={cn("size-2 rounded-full", dot[status])} aria-hidden />
        {label[status]}
      </span>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const mastery = useMastery();
  const due = Object.values(mastery).filter((m) => m.reviewDue).length;
  return (
    <nav aria-label="Main" className="flex h-full flex-col">
      <Link to="/" onClick={onNavigate} className="mb-6 flex items-center gap-2.5 px-3 pt-1">
        <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
          <rect width="32" height="32" rx="8" fill="var(--gw-text)" />
          <path d="M7 22h18M9 22V14l7-5 7 5v8" fill="none" stroke="var(--gw-accent)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="16" cy="17" r="2.2" fill="var(--gw-accent)" />
        </svg>
        <span className="leading-tight">
          <span className="block text-[15px] font-semibold tracking-tight">Groundwork</span>
          <span className="block text-[11.5px] text-muted">Learn from first principles</span>
        </span>
      </Link>
      <ul className="space-y-0.5">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-[14px] transition-colors",
                  isActive ? "bg-surface text-text shadow-card ring-1 ring-border" : "text-muted hover:bg-surface/70 hover:text-text",
                )
              }
            >
              <Icon className="size-4.5 shrink-0" aria-hidden />
              <span className="flex-1">{label}</span>
              {to === "/review" && due > 0 && (
                <span className="rounded-full bg-accent px-1.5 text-[11px] font-semibold text-accent-fg" aria-label={`${due} due`}>
                  {due}
                </span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="mt-auto rounded-xl border border-border bg-surface/60 p-3 text-[12px] leading-relaxed text-muted">
        Local-first: lessons, Python and your progress run on this device. Nothing is uploaded.
      </div>
    </nav>
  );
}

export function AppShell({ children }: { children?: ReactNode }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  const theme = useProgressSelector((p) => p.settings.theme);
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");
  const isDark = theme === "dark" || (theme === "system" && prefersDark);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      } else if (
        e.key === "/" &&
        !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || (e.target as HTMLElement).isContentEditable)
      ) {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => setDrawer(false), [location.pathname]);

  return (
    <div className="min-h-screen bg-bg">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <ThemeController />
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-border bg-bg px-3 py-4 lg:block">
        <SidebarContent />
      </aside>
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 w-72 border-r border-border bg-bg px-3 py-4 shadow-pop">
            <button className="absolute right-3 top-3 rounded p-1 text-muted" onClick={() => setDrawer(false)} aria-label="Close navigation">
              <X className="size-5" />
            </button>
            <SidebarContent onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      )}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-bg/85 px-4 backdrop-blur md:px-8">
          <button className="rounded-md p-1.5 text-muted hover:bg-surface-2 lg:hidden" onClick={() => setDrawer(true)} aria-label="Open navigation">
            <Menu className="size-5" />
          </button>
          <button
            onClick={() => setSearchOpen(true)}
            className="flex h-9 w-full max-w-md items-center gap-2 rounded-lg border border-border bg-surface px-3 text-[13.5px] text-faint shadow-card hover:border-border-strong"
            aria-label="Search (Control+K)"
          >
            <Search className="size-4" aria-hidden />
            <span className="flex-1 text-left">Search everything…</span>
            <span className="hidden sm:inline">
              <Kbd>Ctrl</Kbd> <Kbd>K</Kbd>
            </span>
          </button>
          <div className="ml-auto flex items-center gap-2">
            <RuntimeIndicator />
            <button
              className="rounded-md p-2 text-muted hover:bg-surface-2 hover:text-text"
              onClick={() => progressStore.update((p, now) => updateSettings(p, { theme: isDark ? "light" : "dark" }, now))}
              aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
            >
              {isDark ? <Sun className="size-4.5" /> : <Moon className="size-4.5" />}
            </button>
          </div>
        </header>
        <ContentIssuesBanner />
        <main id="main" className="px-4 py-8 md:px-8 lg:px-10">
          {children ?? <Outlet />}
        </main>
      </div>
      <SearchDialog open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
