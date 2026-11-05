// CodeMirror 6 editor for Python with run shortcut and error-line highlighting.
// Keyboard: Ctrl/Cmd+Enter runs; Tab indents; press Esc then Tab to move focus out.
import { useEffect, useRef } from "react";
import { EditorState, StateEffect, StateField, type Extension } from "@codemirror/state";
import {
  EditorView,
  Decoration,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  drawSelection,
  type DecorationSet,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { indentOnInput, bracketMatching, syntaxHighlighting } from "@codemirror/language";
import { closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
import { python } from "@codemirror/lang-python";
import { classHighlighter } from "@lezer/highlight";
import { cn } from "./ui";

const setMarkedLine = StateEffect.define<{ line: number | null; kind: "error" | "trace" }>();

const markedLineField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    deco = deco.map(tr.changes);
    for (const effect of tr.effects) {
      if (effect.is(setMarkedLine)) {
        const { line, kind } = effect.value;
        if (line === null || line < 1 || line > tr.state.doc.lines) return Decoration.none;
        const from = tr.state.doc.line(line).from;
        return Decoration.set([Decoration.line({ class: kind === "error" ? "cm-error-line" : "cm-trace-line" }).range(from)]);
      }
    }
    if (tr.docChanged) return Decoration.none;
    return deco;
  },
  provide: (f) => EditorView.decorations.from(f),
});

export interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  onRun?: () => void;
  errorLine?: number | null;
  readOnly?: boolean;
  label: string;
  minLines?: number;
  className?: string;
  fontSize?: number;
}

export function CodeEditor({ value, onChange, onRun, errorLine = null, readOnly = false, label, minLines = 4, className, fontSize = 14 }: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const onRunRef = useRef(onRun);
  onChangeRef.current = onChange;
  onRunRef.current = onRun;

  useEffect(() => {
    if (!host.current) return;
    const extensions: Extension[] = [
      lineNumbers(),
      highlightActiveLineGutter(),
      history(),
      drawSelection(),
      indentOnInput(),
      bracketMatching(),
      closeBrackets(),
      highlightActiveLine(),
      python(),
      syntaxHighlighting(classHighlighter),
      markedLineField,
      EditorState.tabSize.of(4),
      EditorView.lineWrapping,
      EditorState.readOnly.of(readOnly),
      EditorView.contentAttributes.of({ "aria-label": label, "aria-multiline": "true" }),
      keymap.of([
        {
          key: "Mod-Enter",
          run: () => {
            onRunRef.current?.();
            return true;
          },
        },
        ...closeBracketsKeymap,
        ...defaultKeymap,
        ...historyKeymap,
        indentWithTab,
      ]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) onChangeRef.current(update.state.doc.toString());
      }),
      EditorView.theme({ ".cm-content": { minHeight: `${minLines * 1.6}em`, padding: "10px 0" } }),
    ];
    view.current = new EditorView({ state: EditorState.create({ doc: value, extensions }), parent: host.current });
    return () => {
      view.current?.destroy();
      view.current = null;
    };
    // The editor is created once; external value changes are synced below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, label]);

  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== value) {
      v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } });
    }
  }, [value]);

  useEffect(() => {
    view.current?.dispatch({ effects: setMarkedLine.of({ line: errorLine, kind: "error" }) });
  }, [errorLine]);

  return <div ref={host} className={cn("gw-editor overflow-hidden", className)} style={{ ["--gw-editor-font-size" as string]: `${fontSize}px` }} />;
}
