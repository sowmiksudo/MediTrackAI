import { useEffect, useState } from "react";
import { Cpu, Database, Search, Shield, Sparkles, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";

interface TelemetryDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function TelemetryDrawer({ open, onClose }: TelemetryDrawerProps) {
  const [status, setStatus] = useState<any>(null);
  const [query, setQuery] = useState("amar abbu er sugar ar gas er osudh ki?");
  const [searchResult, setSearchResult] = useState<any>(null);
  const [searching, setSearching] = useState(false);

  const fetchStatus = async () => {
    try {
      const data = await apiFetch("/api/telemetry/status");
      setStatus(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (open) fetchStatus();
  }, [open]);

  const handleTestRag = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      const data = await apiFetch("/api/rag/search", {
        method: "POST",
        body: JSON.stringify({ query, top_k: 5, synthesize_answer: true }),
      });
      setSearchResult(data);
      fetchStatus();
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
    }
  };

  if (!open) return null;

  const rt = status?.runtime;
  const trace = searchResult?.trace || status?.traces?.latest_rag;
  const piiDiff = status?.traces?.latest_pii_diff;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs">
      <div className="h-full w-full max-w-xl bg-background border-l shadow-2xl flex flex-col">
        <div className="flex items-center justify-between border-b px-5 py-4 bg-card">
          <div className="flex items-center gap-2">
            <Cpu className="h-5 w-5 text-primary" />
            <div>
              <h2 className="font-bold text-base">AI Engineering &amp; Grounding Telemetry</h2>
              <p className="text-xs text-muted-foreground">Live Hybrid RAG, PDPA PII Masking &amp; Runtime Mode</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-auto p-5 space-y-5 text-sm">
          {/* Runtime Mode & GPU VRAM */}
          <Card className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-primary" /> Active Runtime
              </span>
              <Badge variant={rt?.inference_mode === "hybrid_gpu" ? "default" : "secondary"}>
                {rt?.inference_mode === "hybrid_gpu" ? "Hybrid Local GPU (RTX 5050)" : "Cloud-Only Mode (Mac/API)"}
              </Badge>
            </div>
            {rt?.vram && (
              <div className="rounded bg-muted p-2 text-xs">
                <strong>GPU:</strong> {rt.vram.gpu_name} · <strong>VRAM:</strong> {rt.vram.used_mb} MB / {rt.vram.total_mb} MB
              </div>
            )}
            {rt && (
              <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground pt-1">
                <div><strong>Embedder:</strong> {rt.active_embedder}</div>
                <div><strong>Reranker:</strong> {rt.active_reranker}</div>
                <div><strong>ASR:</strong> {rt.active_asr}</div>
                <div><strong>PII Shield:</strong> {rt.active_pii_scrubber}</div>
              </div>
            )}
          </Card>

          {/* PDPA Local PII Redaction Proof */}
          <Card className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold flex items-center gap-1.5">
                <Shield className="h-4 w-4 text-emerald-600" /> PDPA 2026 PII Redaction Diff
              </span>
              {piiDiff && <Badge variant="outline">{piiDiff.engine} ({piiDiff.latency_ms} ms)</Badge>}
            </div>
            {piiDiff ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                <div className="rounded border bg-red-50/60 p-2">
                  <div className="font-semibold text-red-700 mb-1">Raw User Input</div>
                  <p className="text-slate-700 break-words">{piiDiff.raw_text}</p>
                </div>
                <div className="rounded border bg-emerald-50/60 p-2">
                  <div className="font-semibold text-emerald-700 mb-1">Cloud-Safe Redacted</div>
                  <p className="text-slate-700 break-words">{piiDiff.redacted_text}</p>
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">Send a voice or text check-in to inspect live PII redaction.</p>
            )}
          </Card>

          {/* Interactive Cross-Lingual Hybrid RAG Probe */}
          <Card className="p-4 space-y-3">
            <div className="font-semibold flex items-center gap-1.5">
              <Database className="h-4 w-4 text-primary" /> Live Hybrid RAG Probe (Banglish → English)
            </div>
            <form onSubmit={handleTestRag} className="flex gap-2">
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask in Bangla, Banglish, or English..." />
              <Button type="submit" disabled={searching} size="sm">
                <Search className="h-4 w-4 mr-1" /> {searching ? "..." : "Run"}
              </Button>
            </form>

            {searchResult?.answer && (
              <div className="rounded-md bg-primary/5 border border-primary/20 p-3 text-xs leading-relaxed">
                <div className="font-semibold text-primary mb-1">Grounded Answer</div>
                {searchResult.answer}
              </div>
            )}

            {trace && (
              <div className="space-y-2 text-xs">
                <div className="flex flex-wrap gap-1.5 text-muted-foreground">
                  <Badge variant="outline">Latency: {trace.latency_ms} ms</Badge>
                  <Badge variant="outline">{trace.embedding_backend}</Badge>
                  <Badge variant="outline">{trace.reranker_backend}</Badge>
                </div>
                <div className="text-[11px] text-muted-foreground">
                  <strong>Expanded Query:</strong> {trace.expanded_query}
                </div>
                <div className="space-y-1.5 max-h-60 overflow-auto">
                  {(trace.hits || []).map((h: any, idx: number) => (
                    <div key={idx} className="rounded border p-2 bg-card">
                      <div className="flex items-center justify-between font-medium text-primary mb-1">
                        <span>{h.citation}</span>
                        <span>Final: {h.final_score}</span>
                      </div>
                      <p className="text-slate-700 line-clamp-2 mb-1">{h.chunk_text}</p>
                      <div className="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
                        <span>Vec: {h.vec_score}</span>
                        <span>BM25: {h.bm25_score}</span>
                        <span>Trgm: {h.trgm_score}</span>
                        <span>Decay: {h.temporal_decay}</span>
                        <span>Rerank: {h.rerank_score}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
