import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Activity, AlertTriangle, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { BACKEND_URL } from "@/lib/api";

export default function PublicBrief() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetch(`${BACKEND_URL}/api/public/brief/${encodeURIComponent(token)}`)
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail || "Unable to load shared brief");
        setData(body);
      })
      .catch((e) => setError(e.message));
  }, [token]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-slate-50">
        <Card className="max-w-md p-6 text-center space-y-2">
          <AlertTriangle className="h-8 w-8 text-destructive mx-auto" />
          <h1 className="font-bold text-lg">Brief Link Unavailable</h1>
          <p className="text-sm text-muted-foreground">{error}</p>
        </Card>
      </div>
    );
  }

  if (!data) {
    return <div className="min-h-screen flex items-center justify-center text-muted-foreground">Loading Doctor Brief...</div>;
  }

  const brief = data.brief_payload || {};
  const egfr = data.deterministic_scores?.egfr_ckd_epi;

  return (
    <div className="min-h-screen bg-slate-50 py-6 px-4">
      <div className="mx-auto max-w-3xl space-y-4">
        <Card className="p-5 border-t-4 border-t-primary space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              <h1 className="text-xl font-bold">MediTrackAI — Doctor Consultation Brief</h1>
            </div>
            <Badge variant="outline" className="gap-1">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Read-Only Shared View
            </Badge>
          </div>
          <div className="text-sm text-slate-700 bg-slate-100 rounded p-3">
            <strong>Patient:</strong> {data.patient_display_name} ({data.sex || "N/A"}) ·{" "}
            <strong>Conditions:</strong> {(data.chronic_conditions || []).join(", ") || "None"} ·{" "}
            <strong>Allergies:</strong> {(data.allergies || []).join(", ") || "None"}
          </div>

          <p className="text-sm">{brief.patient_snapshot}</p>
          {egfr?.status === "computed" && (
            <div className="text-xs font-medium text-primary">
              CKD-EPI 2021 eGFR: {egfr.egfr_ml_min} mL/min/1.73m² ({egfr.kdigo_stage})
            </div>
          )}

          {brief.ddi_alerts?.length > 0 && (
            <div className="rounded border border-amber-500 bg-amber-50 p-3 text-xs text-amber-950">
              <strong>Interaction / Duplicate Alerts:</strong>
              {brief.ddi_alerts.map((a: any, i: number) => (
                <div key={i}>• {a.clinical_note}</div>
              ))}
            </div>
          )}

          <div>
            <h2 className="font-bold text-xs uppercase text-muted-foreground mb-2">Active Medications</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              {(brief.active_medications || []).map((m: any, i: number) => (
                <div key={i} className="rounded border p-2">
                  <strong>{m.brand_name} {m.dosage}</strong> — {m.generic_name || "Unverified"} ({m.frequency_bd})
                </div>
              ))}
            </div>
          </div>

          <div>
            <h2 className="font-bold text-xs uppercase text-muted-foreground mb-1">Normalized Lab Trends</h2>
            <p className="text-sm">{brief.lab_trends_narrative}</p>
          </div>

          <p className="text-[11px] text-muted-foreground border-t pt-2">{brief.disclaimer}</p>
        </Card>
      </div>
    </div>
  );
}
