import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Calendar, ExternalLink, FlaskConical, Heart, Pill, Stethoscope } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/context/AuthContext";
import { apiFetch, backendUrl } from "@/lib/api";

export default function Summaries() {
  const { activeProfile } = useAuth();
  const [checkIns, setCheckIns] = useState<any[]>([]);
  const [prescriptions, setPrescriptions] = useState<any[]>([]);
  const [reports, setReports] = useState<any[]>([]);
  const [trends, setTrends] = useState<any[]>([]);
  const [detScores, setDetScores] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeProfile) return;
    setLoading(true);
    Promise.all([
      apiFetch("/checkins/summaries?limit=20"),
      apiFetch("/api/prescriptions/summaries?limit=20"),
      apiFetch("/api/reports/summaries?limit=20"),
      apiFetch("/api/reports/trends"),
    ])
      .then(([ci, rx, lab, tr]) => {
        setCheckIns(ci.checkins || []);
        setPrescriptions(rx.prescriptions || []);
        setReports(lab.reports || []);
        setTrends(tr.trends || []);
        setDetScores(tr.deterministic_scores || null);
      })
      .catch((err) => console.error(err))
      .finally(() => setLoading(false));
  }, [activeProfile?.id]);

  const scoreBadgeVariant = (score: string) => {
    const s = (score || "").toLowerCase();
    if (s === "positive") return "default" as const;
    if (s === "negative") return "destructive" as const;
    return "secondary" as const;
  };

  if (loading) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        Loading longitudinal records for {activeProfile?.display_name}...
      </div>
    );
  }

  const egfr = detScores?.egfr_ckd_epi;
  const gly = detScores?.glycemic_band;

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Longitudinal Health Records</h1>
          <p className="text-sm text-muted-foreground">
            Normalized trends, DGDA medication history, and voice summaries for <strong>{activeProfile?.display_name}</strong>
          </p>
        </div>
      </div>

      {/* Deterministic Clinical Calculators (No arbitrary LLM %) */}
      {detScores && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Card className="p-4 flex items-center justify-between">
            <div>
              <div className="text-xs font-medium text-muted-foreground">CKD-EPI 2021 eGFR (Deterministic)</div>
              <div className="text-lg font-bold mt-0.5">
                {egfr?.status === "computed"
                  ? `${egfr.egfr_ml_min} mL/min/1.73m²`
                  : "Insufficient data"}
              </div>
              <div className="text-xs text-muted-foreground">
                {egfr?.status === "computed"
                  ? egfr.kdigo_stage
                  : `Missing: ${(egfr?.missing_inputs || []).join(", ")}`}
              </div>
            </div>
            <Badge variant={egfr?.metformin_caution ? "destructive" : "outline"}>
              {egfr?.metformin_contraindicated
                ? "Metformin Hold Alert"
                : egfr?.metformin_caution
                ? "Renal Dose Review"
                : "Formula Grounded"}
            </Badge>
          </Card>

          <Card className="p-4 flex items-center justify-between">
            <div>
              <div className="text-xs font-medium text-muted-foreground">ADA Glycemic Status (mmol/L Native)</div>
              <div className="text-lg font-bold mt-0.5">
                {gly?.status === "computed" ? gly.band : "Insufficient glycemic labs"}
              </div>
              <div className="text-xs text-muted-foreground">{gly?.summary || "Upload HbA1c or Fasting Glucose"}</div>
            </div>
            <Activity className="h-5 w-5 text-primary shrink-0" />
          </Card>
        </div>
      )}

      <Tabs defaultValue="trends">
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="trends" className="gap-1.5"><FlaskConical className="h-4 w-4" /> Lab Trends ({trends.length})</TabsTrigger>
          <TabsTrigger value="prescriptions" className="gap-1.5"><Stethoscope className="h-4 w-4" /> Prescriptions ({prescriptions.length})</TabsTrigger>
          <TabsTrigger value="reports" className="gap-1.5"><Calendar className="h-4 w-4" /> Lab Reports ({reports.length})</TabsTrigger>
          <TabsTrigger value="checkins" className="gap-1.5"><Heart className="h-4 w-4" /> Check-Ins ({checkIns.length})</TabsTrigger>
        </TabsList>

        {/* Normalized Multi-Date Recharts Trends */}
        <TabsContent value="trends" className="space-y-4 mt-4">
          {trends.length === 0 ? (
            <Card className="p-8 text-center text-muted-foreground">No normalized numeric lab observations yet.</Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {trends.map((series, idx) => (
                <Card key={idx} className="p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-sm">{series.metric_name}</h3>
                      <p className="text-xs text-muted-foreground">
                        Canonical Unit: <strong>{series.unit || "N/A"}</strong> {series.loinc_code && `· LOINC ${series.loinc_code}`}
                      </p>
                    </div>
                    <Badge variant="outline">
                      Latest: {series.points[series.points.length - 1]?.value} {series.unit}
                    </Badge>
                  </div>
                  <div className="h-44 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={series.points}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} width={42} />
                        <Tooltip />
                        <Line type="monotone" dataKey="value" stroke="#0f4c81" strokeWidth={2.5} dot={{ r: 4 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Prescriptions + BD Generic + DDI Alerts */}
        <TabsContent value="prescriptions" className="space-y-4 mt-4">
          {prescriptions.map((rx) => (
            <Card key={rx.id} className="p-5 space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-bold text-base">
                    {rx.doctor_name || "Doctor Prescription"} {rx.doctor_qualification && `(${rx.doctor_qualification})`}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {rx.hospital || "Chamber"} · {rx.prescription_date || rx.timestamp?.slice(0, 10)}
                    {rx.doctor_bmdc_reg && ` · BMDC: ${rx.doctor_bmdc_reg}`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={rx.verification_status === "confirmed" ? "default" : "secondary"}>
                    {rx.verification_status === "confirmed" ? "Verified" : "Pending Review"}
                  </Badge>
                  {rx.file_url && (
                    <a href={backendUrl(rx.file_url)} target="_blank" rel="noreferrer" className="text-xs text-primary flex items-center gap-1 hover:underline">
                      File <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </div>

              {rx.ddi_alerts?.length > 0 && (
                <div className="rounded border border-amber-500 bg-amber-50 p-3 text-xs text-amber-950 space-y-1">
                  {rx.ddi_alerts.map((a: any, i: number) => (
                    <div key={i} className="flex items-start gap-1.5">
                      <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                      <span><strong>[{a.rule_type}]</strong> {a.clinical_note}</span>
                    </div>
                  ))}
                </div>
              )}

              {rx.prescription_summary && <p className="text-sm text-slate-700 bg-muted/50 p-3 rounded">{rx.prescription_summary}</p>}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(rx.medicines || []).map((m: any, mi: number) => (
                  <div key={mi} className="rounded border p-2.5 flex items-start gap-2 text-xs">
                    <Pill className="h-4 w-4 text-emerald-600 mt-0.5 shrink-0" />
                    <div>
                      <div className="font-semibold text-sm">{m.brand_name} {m.dosage}</div>
                      <div className="text-primary">{m.generic_name || "Unverified generic"}</div>
                      <div className="text-muted-foreground">
                        Schedule: {m.frequency_bd || "-"} {m.special_instructions && `· ${m.special_instructions}`}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </TabsContent>

        {/* Normalized Lab Reports */}
        <TabsContent value="reports" className="space-y-4 mt-4">
          {reports.map((rep) => (
            <Card key={rep.id} className="p-5 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold text-base">{rep.lab_name || "Diagnostic Lab Report"}</h3>
                  <p className="text-xs text-muted-foreground">Report Date: {rep.report_date || rep.timestamp?.slice(0, 10)}</p>
                </div>
                {rep.file_url && (
                  <a href={backendUrl(rep.file_url)} target="_blank" rel="noreferrer" className="text-xs text-primary flex items-center gap-1 hover:underline">
                    View Report <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
              {rep.lab_summary_overview && <p className="text-sm bg-muted/50 p-3 rounded">{rep.lab_summary_overview}</p>}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(rep.metrics || []).map((m: any, mi: number) => (
                  <div key={mi} className="rounded border p-2.5 flex justify-between items-center text-xs">
                    <div>
                      <div className="font-semibold text-sm">{m.test_name}</div>
                      <div className="text-muted-foreground">Raw: {m.raw_value} {m.raw_unit} · Ref: {m.reference_range}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-sm">{m.value} {m.unit}</div>
                      <Badge variant={m.flag === "normal" ? "outline" : "destructive"} className="text-[10px] uppercase">{m.flag}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </TabsContent>

        {/* Bilingual Check-Ins */}
        <TabsContent value="checkins" className="space-y-4 mt-4">
          {checkIns.map((ci) => (
            <Card key={ci.id} className="p-5 space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold">{ci.timestamp?.slice(0, 10)} · Mood: {ci.mood}</div>
                <div className="flex gap-1.5">
                  <Badge variant="outline" className="text-[10px]">{ci.language_detected}</Badge>
                  <Badge variant={scoreBadgeVariant(ci.overall_score)} className="capitalize">{ci.overall_score}</Badge>
                </div>
              </div>
              <p className="text-sm text-slate-700 bg-muted/50 p-3 rounded">{ci.summary}</p>
              {ci.symptoms?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {ci.symptoms.map((s: string, si: number) => (
                    <Badge key={si} variant="outline" className="text-xs">{s}</Badge>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
}
