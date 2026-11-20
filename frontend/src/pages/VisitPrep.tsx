import { useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, FileDown, Loader2, PhoneCall, QrCode, Share2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useAuth } from "@/context/AuthContext";
import { apiFetch, backendUrl, getStoredToken, JobProgressEvent, subscribeJobProgress } from "@/lib/api";

const BD_HOTLINES = [
  { name: "Bangladesh National Emergency", phone: "999", note: "Ambulance & Emergency Response" },
  { name: "Square Hospital Dhaka", phone: "10616", note: "Panthapath · Cardiology / Medicine / ER" },
  { name: "Evercare Hospital Dhaka", phone: "10678", note: "Bashundhara R/A · Multi-specialty" },
  { name: "United Hospital Dhaka", phone: "10666", note: "Gulshan · Cardiac / Nephrology / Oncology" },
  { name: "Labaid Specialized Hospital", phone: "10606", note: "Dhanmondi · Diagnostic & Cardiac" },
  { name: "Ibn Sina Trust Hotline", phone: "10615", note: "Dhanmondi / Kalyanpur · Clinics & Labs" },
];

export default function VisitPrep() {
  const { activeProfile } = useAuth();
  const [brief, setBrief] = useState<any>(null);
  const [jobState, setJobState] = useState<JobProgressEvent | null>(null);
  const [generating, setGenerating] = useState(false);

  const loadLatest = async () => {
    try {
      const data = await apiFetch("/api/briefs/latest");
      setBrief(data);
    } catch {
      setBrief(null);
    }
  };

  useEffect(() => {
    if (activeProfile) loadLatest();
  }, [activeProfile?.id]);

  const handleGenerate = async () => {
    setGenerating(true);
    setJobState({ job_id: "", status: "queued", progress_pct: 5, current_step: "Starting Parallel Clinical Brief DAG..." });
    try {
      const data = await apiFetch("/api/briefs/generate", { method: "POST" });
      subscribeJobProgress(data.job_id, (ev) => {
        setJobState(ev);
        if (ev.status === "completed") {
          setGenerating(false);
          loadLatest();
          toast.success("1-Page English Doctor Brief ready!");
        } else if (ev.status === "failed") {
          setGenerating(false);
          toast.error(ev.error_message || "Failed to generate brief");
        }
      });
    } catch (err: any) {
      setGenerating(false);
      toast.error(err.message || "Error starting brief generation");
    }
  };

  const handleDownloadPdf = async () => {
    if (!brief?.id) return;
    try {
      const res = await fetch(backendUrl(`/api/briefs/${brief.id}/pdf`), {
        headers: {
          Authorization: `Bearer ${getStoredToken() || ""}`,
          "X-Profile-Id": activeProfile?.id || "",
        },
      });
      if (!res.ok) throw new Error("PDF download failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `MediTrack_DoctorBrief_${activeProfile?.display_name || "Patient"}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      toast.error(err.message);
    }
  };

  const shareUrl = brief?.share_url || (brief?.share_token ? `${window.location.origin}/brief/${brief.share_token}` : "");
  const whatsappHref = shareUrl
    ? `https://wa.me/?text=${encodeURIComponent(`MediTrackAI 1-Page Clinical Brief for ${activeProfile?.display_name}: ${shareUrl}`)}`
    : "#";

  const payload = brief?.brief_payload;

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Doctor Visit Prep &amp; 1-Page Brief</h1>
          <p className="text-sm text-muted-foreground">
            Concise English clinical dossier + 72h expiring QR &amp; WhatsApp share for{" "}
            <strong>{activeProfile?.display_name}</strong>
          </p>
        </div>
        <Button onClick={handleGenerate} disabled={generating} className="gap-2">
          {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {generating ? "Generating..." : "Generate 1-Page Doctor Brief"}
        </Button>
      </div>

      {jobState && generating && (
        <Card className="p-4 space-y-2">
          <div className="flex justify-between text-xs font-medium">
            <span>{jobState.current_step}</span>
            <span>{jobState.progress_pct}%</span>
          </div>
          <Progress value={jobState.progress_pct} />
        </Card>
      )}

      {payload ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* 1-Page English Clinical Brief Preview */}
          <Card className="lg:col-span-2 p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
              <div>
                <h2 className="text-lg font-bold text-primary">1-Page English Clinical Brief</h2>
                <p className="text-xs text-muted-foreground">
                  Generated {brief.created_at?.slice(0, 16).replace("T", " ")}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={handleDownloadPdf} className="gap-1.5">
                  <FileDown className="h-4 w-4" /> WeasyPrint PDF
                </Button>
                {shareUrl && (
                  <a href={whatsappHref} target="_blank" rel="noreferrer">
                    <Button size="sm" className="gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white">
                      <Share2 className="h-4 w-4" /> WhatsApp Share
                    </Button>
                  </a>
                )}
              </div>
            </div>

            {payload.red_flag_summary?.length > 0 && (
              <div className="rounded border border-red-400 bg-red-50 p-3 text-xs text-red-900 space-y-1">
                <div className="font-bold flex items-center gap-1.5"><AlertTriangle className="h-4 w-4" /> Red Flags</div>
                {payload.red_flag_summary.map((x: string, i: number) => <div key={i}>• {x}</div>)}
              </div>
            )}

            <div className="space-y-1">
              <div className="text-xs font-bold uppercase text-muted-foreground">Patient Snapshot</div>
              <p className="text-sm">{payload.patient_snapshot}</p>
              <p className="text-xs text-muted-foreground">{payload.chief_concerns_summary}</p>
            </div>

            <div className="space-y-1.5">
              <div className="text-xs font-bold uppercase text-muted-foreground">Active Medications (BD Brands → Generics)</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(payload.active_medications || []).map((m: any, i: number) => (
                  <div key={i} className="rounded border p-2 text-xs flex justify-between items-start">
                    <div>
                      <div className="font-semibold">{m.brand_name} {m.dosage}</div>
                      <div className="text-primary">{m.generic_name || "Unverified"} · {m.frequency_bd}</div>
                    </div>
                    {m.flag && <Badge variant={m.flag.includes("DDI") ? "destructive" : "outline"} className="text-[10px]">{m.flag}</Badge>}
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <div className="text-xs font-bold uppercase text-muted-foreground">Normalized Lab Trends</div>
              <p className="text-sm">{payload.lab_trends_narrative}</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="rounded bg-muted/50 p-3 space-y-1">
                <div className="font-bold">Clinical Observations</div>
                {(payload.clinical_observations || []).map((o: string, i: number) => <div key={i}>• {o}</div>)}
              </div>
              <div className="rounded bg-primary/5 p-3 space-y-1">
                <div className="font-bold text-primary">Questions for Your Doctor</div>
                {(payload.questions_for_doctor || []).map((q: string, i: number) => <div key={i}>• {q}</div>)}
              </div>
            </div>

            <p className="text-[11px] text-muted-foreground border-t pt-2">{payload.disclaimer}</p>
          </Card>

          {/* QR Share & BD Hospital Hotlines */}
          <div className="space-y-4">
            <Card className="p-4 text-center space-y-3">
              <div className="flex items-center justify-center gap-1.5 font-semibold text-sm">
                <QrCode className="h-4 w-4 text-primary" /> Doctor QR Link (72h TTL)
              </div>
              {shareUrl && (
                <>
                  <div className="mx-auto w-36 h-36 rounded border p-2 bg-white flex items-center justify-center">
                    <img
                      src={brief.qr_data_uri || backendUrl(`/api/briefs/${brief.id}/qr.png`)}
                      alt="Brief QR"
                      className="w-full h-full object-contain"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display = "none";
                      }}
                    />
                  </div>
                  <a href={shareUrl} target="_blank" rel="noreferrer" className="text-xs text-primary inline-flex items-center gap-1 hover:underline break-all">
                    Open Public Doctor View <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                </>
              )}
            </Card>

            <Card className="p-4 space-y-2.5">
              <h3 className="font-bold text-sm">Bangladesh Hospital &amp; Emergency Hotlines</h3>
              <div className="space-y-2">
                {BD_HOTLINES.map((h) => (
                  <div key={h.phone} className="flex items-center justify-between text-xs border-b last:border-0 pb-1.5">
                    <div>
                      <div className="font-semibold">{h.name}</div>
                      <div className="text-muted-foreground">{h.note}</div>
                    </div>
                    <a href={`tel:${h.phone}`}>
                      <Button size="sm" variant={h.phone === "999" ? "destructive" : "outline"} className="h-7 px-2.5 gap-1">
                        <PhoneCall className="h-3 w-3" /> {h.phone}
                      </Button>
                    </a>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      ) : (
        <Card className="p-8 text-center space-y-3">
          <p className="text-muted-foreground text-sm">
            No Doctor Brief generated yet for <strong>{activeProfile?.display_name}</strong>.
          </p>
          <Button onClick={handleGenerate} disabled={generating}>
            Generate 1-Page English Doctor Brief
          </Button>
        </Card>
      )}
    </div>
  );
}
