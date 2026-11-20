import { useEffect, useId, useState } from "react";
import { Code2, Eye } from "lucide-react";

let mermaidInitialized = false;

export function MermaidDiagram({ code }: { code: string }) {
  const reactId = useId().replace(/:/g, "_");
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [showSource, setShowSource] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function render() {
      if (!code?.trim()) {
        setSvg("");
        return;
      }
      try {
        const mod = await import("mermaid");
        const mermaid = mod.default;
        if (!mermaidInitialized) {
          mermaid.initialize({
            startOnLoad: false,
            theme: "neutral",
            securityLevel: "strict",
            flowchart: { useMaxWidth: true, htmlLabels: false },
          });
          mermaidInitialized = true;
        }
        const { svg: rendered } = await mermaid.render(`mmd_${reactId}`, code.trim());
        if (!cancelled) {
          setSvg(rendered);
          setError("");
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || "Unable to render diagram");
        }
      }
    }
    render();
    return () => {
      cancelled = true;
    };
  }, [code, reactId]);

  if (!code?.trim()) return null;

  return (
    <div className="mt-4 rounded-xl border border-border bg-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-2 text-xs">
        <span className="font-semibold text-muted-foreground">Live Rendered Architecture / Flow Diagram</span>
        <button
          type="button"
          onClick={() => setShowSource((s) => !s)}
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          {showSource ? <Eye className="h-3.5 w-3.5" /> : <Code2 className="h-3.5 w-3.5" />}
          {showSource ? "Diagram" : "Mermaid Source"}
        </button>
      </div>
      {showSource || error ? (
        <div className="p-3">
          {error && <p className="mb-2 text-xs text-amber-600">Diagram notice: {error}</p>}
          <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 text-xs font-mono text-slate-100">{code}</pre>
        </div>
      ) : svg ? (
        <div
          className="overflow-x-auto p-4 flex justify-center bg-white"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        <div className="p-6 text-center text-xs text-muted-foreground">Rendering diagram...</div>
      )}
    </div>
  );
}
