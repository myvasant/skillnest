import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Keeps one broken screen from taking down the whole app; progress is unaffected. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Screen crashed", error, info.componentStack);
  }

  override render() {
    if (!this.state.error) return this.props.children;
    const chunkError = /Failed to fetch dynamically imported module|Importing a module script failed/i.test(this.state.error.message);
    return (
      <div role="alert" className="mx-auto max-w-xl rounded-xl border border-danger/30 bg-danger-soft/50 p-6 text-[14px]">
        <h1 className="text-lg font-semibold text-danger">This screen hit a problem</h1>
        <p className="mt-2 text-text">
          {chunkError
            ? "Part of the app could not be loaded. If the development server was restarted or the app was updated, reload the page."
            : "Something went wrong while showing this page. Your saved progress is not affected."}
        </p>
        <pre className="mt-3 overflow-auto rounded bg-surface p-2 font-mono text-[12px] text-muted">{this.state.error.message}</pre>
        <div className="mt-4 flex gap-2">
          <button className="rounded-lg bg-accent px-3 py-1.5 font-medium text-accent-fg" onClick={() => window.location.reload()}>
            Reload
          </button>
          <button className="rounded-lg border border-border px-3 py-1.5" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      </div>
    );
  }
}
