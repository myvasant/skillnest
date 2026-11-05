import { useRef, useState, useSyncExternalStore } from "react";
import { Download, HardDrive, RotateCcw, ShieldCheck, Upload, Wifi } from "lucide-react";
import { curriculum } from "../../content/runtime";
import { useDocumentTitle, useOnline, usePythonStatus } from "../../lib/hooks";
import { python } from "../../python/client";
import { updateSettings } from "../../storage/actions";
import { createExport, parseExport, summarizeProgress, type Progress, type Settings } from "../../storage/progress";
import { progressStore, useProgress } from "../../storage/store";
import { Badge, Button, Card, PageHeader, SectionHeading, cn } from "../../components/ui";

export const APP_VERSION = "0.1.0";

function Choice<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-3 py-1.5 text-[13px] font-medium",
            value === o.value ? "bg-surface text-text shadow-card" : "text-muted hover:text-text",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function SettingsPage() {
  useDocumentTitle("Settings");
  const progress = useProgress();
  const diagnostics = useSyncExternalStore(progressStore.subscribe, progressStore.getDiagnostics);
  const online = useOnline();
  const pyStatus = usePythonStatus();
  const fileInput = useRef<HTMLInputElement>(null);
  const [pendingImport, setPendingImport] = useState<{ progress: Progress; exportedAt?: string; name: string } | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [resetText, setResetText] = useState("");
  const set = (patch: Partial<Settings>) => progressStore.update((p, now) => updateSettings(p, patch, now));
  const summary = summarizeProgress(progress);

  const exportProgress = () => {
    const data = createExport(progressStore.get(), APP_VERSION);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `groundwork-progress-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setMessage({ tone: "success", text: "Progress exported. Keep the file somewhere safe — it is your backup." });
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
      setMessage({ tone: "danger", text: "That file is too large to be a Groundwork export." });
      return;
    }
    const parsed = parseExport(await file.text());
    if (!parsed.ok) {
      setMessage({ tone: "danger", text: `Import failed: ${parsed.error}` });
      return;
    }
    setPendingImport({ progress: parsed.progress, exportedAt: parsed.exportedAt, name: file.name });
    setMessage(null);
  };

  const confirmImport = () => {
    if (!pendingImport) return;
    progressStore.replace(pendingImport.progress);
    setPendingImport(null);
    setMessage({ tone: "success", text: "Progress restored from the backup file." });
  };

  const incoming = pendingImport ? summarizeProgress(pendingImport.progress) : null;

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Settings & data" description="Preferences, backups and storage. All data stays in this browser unless you export it." />

      {message && (
        <div
          role="status"
          className={cn(
            "mb-6 rounded-lg border px-4 py-3 text-[14px]",
            message.tone === "success" ? "border-success/30 bg-success-soft text-success" : "border-danger/30 bg-danger-soft text-danger",
          )}
        >
          {message.text}
        </div>
      )}
      {(diagnostics.loadWarning || diagnostics.saveError) && (
        <div role="alert" className="mb-6 rounded-lg border border-warning/40 bg-warning-soft px-4 py-3 text-[14px] text-warning">
          {diagnostics.loadWarning ?? diagnostics.saveError}
        </div>
      )}

      <Card className="mb-6 p-5">
        <SectionHeading title="Appearance & accessibility" />
        <div className="space-y-4 text-[14px]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>Theme</span>
            <Choice
              label="Theme"
              value={progress.settings.theme}
              onChange={(theme) => set({ theme })}
              options={[
                { value: "system", label: "System" },
                { value: "light", label: "Light" },
                { value: "dark", label: "Dark" },
              ]}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              Motion <span className="block text-[12.5px] text-muted">“Reduce” turns off animations even if your OS setting allows them.</span>
            </span>
            <Choice
              label="Motion"
              value={progress.settings.motion}
              onChange={(motion) => set({ motion })}
              options={[
                { value: "system", label: "Follow system" },
                { value: "reduce", label: "Reduce" },
              ]}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label htmlFor="font-size">Code editor font size</label>
            <div className="flex items-center gap-3">
              <input
                id="font-size"
                type="range"
                min={11}
                max={22}
                value={progress.settings.editorFontSize}
                onChange={(e) => set({ editorFontSize: Number(e.target.value) })}
                className="accent-[var(--gw-accent)]"
              />
              <span className="w-10 font-mono text-[13px] tabular-nums">{progress.settings.editorFontSize}px</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label htmlFor="deep-dives">Show deep dives in lessons by default</label>
            <input
              id="deep-dives"
              type="checkbox"
              role="switch"
              checked={progress.settings.showDeepDives}
              onChange={(e) => set({ showDeepDives: e.target.checked })}
              className="size-4 accent-[var(--gw-accent)]"
            />
          </div>
        </div>
      </Card>

      <Card className="mb-6 p-5">
        <SectionHeading
          title="Backup and restore"
          description="Export a JSON file containing all your progress, code drafts and settings. Import it on any device."
        />
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={exportProgress} icon={<Download className="size-4" aria-hidden />}>
            Export progress
          </Button>
          <Button onClick={() => fileInput.current?.click()} icon={<Upload className="size-4" aria-hidden />}>
            Import from file…
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(e) => void onFile(e.target.files?.[0]).finally(() => (e.target.value = ""))}
            aria-label="Choose a progress file to import"
            data-testid="import-input"
          />
        </div>
        {pendingImport && incoming && (
          <div className="mt-4 rounded-lg border border-warning/40 bg-warning-soft/60 p-4 text-[14px]">
            <p className="font-semibold">Replace your current progress with “{pendingImport.name}”?</p>
            <p className="mt-1 text-muted">
              Backup from {pendingImport.exportedAt ? new Date(pendingImport.exportedAt).toLocaleString() : "an unknown date"}: {incoming.lessonsStarted}{" "}
              lessons started, {incoming.conceptsMastered} concepts mastered, {incoming.itemsAttempted} questions attempted, {incoming.snippets} snippets.
            </p>
            <p className="mt-1 text-muted">
              Your current data ({summary.lessonsStarted} lessons, {summary.conceptsMastered} mastered) will be overwritten. Export it first if unsure.
            </p>
            <div className="mt-3 flex gap-2">
              <Button variant="primary" onClick={confirmImport}>
                Replace and restore
              </Button>
              <Button onClick={() => setPendingImport(null)}>Cancel</Button>
            </div>
          </div>
        )}
      </Card>

      <Card className="mb-6 p-5">
        <SectionHeading title="Storage diagnostics" />
        <dl className="grid gap-x-6 gap-y-2 text-[14px] sm:grid-cols-2">
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Browser storage</dt>
            <dd>{diagnostics.available ? <Badge tone="success">Available</Badge> : <Badge tone="danger">Unavailable</Badge>}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Progress size</dt>
            <dd className="font-mono">{formatBytes(diagnostics.bytes)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Last saved</dt>
            <dd>{diagnostics.lastSavedAt ? new Date(diagnostics.lastSavedAt).toLocaleTimeString() : "this session: not yet"}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Schema version</dt>
            <dd className="font-mono">v{progress.schemaVersion}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Profile created</dt>
            <dd>{new Date(progress.createdAt).toLocaleDateString()}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Recorded answers</dt>
            <dd className="tabular-nums">{progress.history.length}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Python runtime</dt>
            <dd>
              {pyStatus === "ready" || pyStatus === "busy" ? (
                <Badge tone="success">Ready · Pyodide {python.version}</Badge>
              ) : pyStatus === "error" ? (
                <Badge tone="danger">Failed: {python.getLastError()}</Badge>
              ) : (
                <Badge tone="neutral">{pyStatus}</Badge>
              )}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Network</dt>
            <dd>
              {online ? (
                <Badge tone="success">
                  <Wifi className="size-3" aria-hidden /> Online
                </Badge>
              ) : (
                <Badge tone="warning">Offline</Badge>
              )}
            </dd>
          </div>
        </dl>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void python.restart().catch(() => undefined)} icon={<RotateCcw className="size-3.5" aria-hidden />}>
            Restart Python runtime
          </Button>
        </div>
        <div className="mt-4 rounded-lg bg-surface-2 p-3 text-[13px] text-muted">
          <p className="flex items-center gap-1.5 font-medium text-text">
            <HardDrive className="size-4" aria-hidden /> What needs the internet?
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            <li>
              Nothing for core learning: lessons, the Python standard library, quizzes, search and progress all work offline once the app is running locally.
            </li>
            <li>Loading optional Python packages (numpy, pandas, scikit-learn…) downloads them from the official Pyodide CDN the first time.</li>
            <li>External documentation links open the original websites.</li>
          </ul>
        </div>
      </Card>

      <Card className="mb-6 p-5">
        <SectionHeading title="Privacy" />
        <p className="flex items-start gap-2 text-[14px] text-muted">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
          Groundwork has no accounts, analytics or telemetry. Your progress and code live in this browser's local storage under the key
          <code className="mx-1 rounded bg-surface-2 px-1 font-mono text-[12px]">groundwork:progress</code>. Clearing site data removes it, so export backups
          regularly. The curriculum currently has {curriculum.stats.concepts} concepts and {curriculum.stats.lessons} full lessons.
        </p>
      </Card>

      <Card className="border-danger/40 p-5">
        <SectionHeading
          title="Reset all progress"
          description="Deletes lessons, answers, mastery, reviews, code drafts, snippets and projects from this browser. Theme settings are kept."
        />
        <label htmlFor="reset-confirm" className="text-[13.5px] text-muted">
          Type <strong className="font-mono text-text">RESET</strong> to confirm:
        </label>
        <div className="mt-1.5 flex flex-wrap gap-2">
          <input
            id="reset-confirm"
            value={resetText}
            onChange={(e) => setResetText(e.target.value)}
            className="h-9 rounded-lg border border-border bg-surface px-3 font-mono text-[14px]"
            autoComplete="off"
          />
          <Button
            variant="danger"
            disabled={resetText !== "RESET"}
            onClick={() => {
              progressStore.reset();
              setResetText("");
              setMessage({ tone: "success", text: "All progress was reset." });
            }}
          >
            Delete my progress
          </Button>
        </div>
      </Card>
    </div>
  );
}
