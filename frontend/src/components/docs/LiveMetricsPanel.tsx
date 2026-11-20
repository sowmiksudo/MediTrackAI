import { useState } from "react";
import { Activity, Cpu, Database, RefreshCw, Route } from "lucide-react";

export interface LiveStats {
  generated_at: string;
  inference_mode: string;
  provider_mode: string;
  counts: Record<string, number>;
  telemetry: {
    latest_rag?: any;
    latest_pii_diff?: any;
    recent_voice_events?: any[];
  };
  api_routes: Array<{
    path: string;
    methods: string[];
    tags: string[];
    name: string;
  }>;
}

export function LiveMetricsPanel({
  stats,
  onRefresh,
  refreshing,
}: {
  stats: LiveStats;
  onRefresh?: () => void;
  refreshing?: boolean;
}) {
  const [routeFilter, setRouteFilter] = useState("");
  const counts = stats?.counts || {};
  const filteredRoutes = (stats?.api_routes || []).filter(
    (r) =>
      !routeFilter.trim() ||
      r.path.toLowerCase().includes(routeFilter.toLowerCase()) ||
      r.tags.some((t) => t.toLowerCase().includes(routeFilter.toLowerCase()))
  );

  const statTiles = [
    { label: "Users", val: counts.users ?? 0 },
    { label: "Family Profiles", val: counts.patient_profiles ?? 0 },
    { label: "Prescriptions", val: counts.prescriptions ?? 0 },
    { label: "Lab Reports", val: counts.lab_reports ?? 0 },
    { label: "Voice Check-Ins", val: counts.checkins ?? 0 },
    { label: "Doctor Briefs", val: counts.doctor_briefs ?? 0 },
    { label: "RAG Chunks", val: counts.knowledge_chunks ?? 0 },
    { label: "BD Drugs Seeded", val: counts.bd_drugs ?? 0 },
    { label: "DDI Rules", val: counts.bd_ddi_rules ?? 0 },
    { label: "LOINC Labs", val: counts.loinc_labs ?? 0 },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-emerald-600" />
          <span className="text-sm font-bold text-foreground">Live Application State (Auto-Synced)</span>
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
            <Cpu className="h-3 w-3" />
            Mode: {stats.inference_mode}
          </span>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1 text-xs font-medium hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            Sync Now
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
        {statTiles.map((t) => (
          <div key={t.label} className="rounded-xl border border-border bg-card p-3">
            <div className="text-[11px] text-muted-foreground">{t.label}</div>
            <div className="mt-1 text-xl font-bold text-foreground tabular-nums">{t.val}</div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/40 px-3 py-2.5">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <Route className="h-4 w-4 text-primary" />
            <span>Live Introspected FastAPI Endpoints ({filteredRoutes.length})</span>
          </div>
          <input
            type="text"
            value={routeFilter}
            onChange={(e) => setRouteFilter(e.target.value)}
            placeholder="Filter path or tag..."
            className="h-7 rounded-md border border-border bg-background px-2.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div className="max-h-64 overflow-y-auto divide-y divide-border text-xs">
          {filteredRoutes.map((r, i) => (
            <div key={`${r.path}-${i}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 hover:bg-muted/30">
              <div className="flex items-center gap-2">
                <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-primary">
                  {r.methods.join(", ") || "WS"}
                </span>
                <span className="font-mono text-foreground">{r.path}</span>
              </div>
              <span className="text-[11px] text-muted-foreground">{r.tags.join(", ") || "core"}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <Database className="h-3.5 w-3.5" />
        <span>Last synced: {new Date(stats.generated_at).toLocaleString()}</span>
      </div>
    </div>
  );
}
