import { useState } from "react";
import { AlertTriangle, Camera, CheckCircle2, FileText, Loader2, Plus, Search, Trash2, Upload as UploadIcon } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useAuth } from "@/context/AuthContext";
import { apiFetch, BACKEND_URL, getStoredProfileId, getStoredToken, JobProgressEvent, subscribeJobProgress } from "@/lib/api";

interface VerifiedMed {
  raw_name: string;
  brand_name: string;
  generic_name?: string | null;
  dosage: string;
  frequency_bd: string;
  duration: string;
  special_instructions: string;
  indicative_price_bdt?: number | null;
  confidence: number;
  confidence_tier: string;
  needs_user_confirm: boolean;
  suggestions?: any[];
}

export default function Upload() {
  const { activeProfile } = useAuth();
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [showTypeDialog, setShowTypeDialog] = useState(false);

  const [jobState, setJobState] = useState<JobProgressEvent | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  // HITL Rx Confirmation Modal State
  const [hitlOpen, setHitlOpen] = useState(false);
  const [rxId, setRxId] = useState<number | null>(null);
  const [rxMeds, setRxMeds] = useState<VerifiedMed[]>([]);
  const [rxDdiAlerts, setRxDdiAlerts] = useState<any[]>([]);
  const [rxSummary, setRxSummary] = useState("");
  const [drugQueryIdx, setDrugQueryIdx] = useState<number | null>(null);
  const [drugSearchResults, setDrugSearchResults] = useState<any[]>([]);

  // Lab Result Card State
  const [labResult, setLabResult] = useState<any>(null);

  const onFileSelected = (file?: File) => {
    if (!file) return;
    setPendingFile(file);
    setShowTypeDialog(true);
  };

  const handleUpload = async (docType: "prescription" | "lab_report") => {
    if (!pendingFile) return;
    setShowTypeDialog(false);
    setIsProcessing(true);
    setLabResult(null);
    setJobState({ job_id: "", status: "queued", progress_pct: 5, current_step: "Uploading document..." });

    try {
      const form = new FormData();
      form.append("file", pendingFile);

      const endpoint = docType === "prescription" ? "/upload-prescription" : "/upload-lab-report";
      const res = await fetch(`${BACKEND_URL}${endpoint}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${getStoredToken() || ""}`,
          "X-Profile-Id": getStoredProfileId() || "",
        },
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.message || "Upload failed");

      const unsub = subscribeJobProgress(
        data.job_id,
        (ev) => {
          setJobState(ev);
          if (ev.status === "completed") {
            setIsProcessing(false);
            const payload = ev.result_payload || {};
            if (docType === "prescription") {
              setRxId(payload.prescription_id);
              setRxMeds(
                (payload.medicines || []).map((m: any) => ({
                  ...m,
                  raw_name: m.brand_name || m.raw_name,
                }))
              );
              setRxDdiAlerts(payload.ddi_alerts || []);
              setRxSummary(payload.summary || "");
              setHitlOpen(true);
              toast.success("Prescription parsed — please confirm medicines");
            } else {
              setLabResult(payload);
              toast.success("Lab report normalized & indexed!");
            }
          } else if (ev.status === "failed") {
            setIsProcessing(false);
            toast.error(ev.error_message || "Extraction failed");
          }
        },
        () => {
          setIsProcessing(false);
        }
      );
      void unsub;
    } catch (err: any) {
      setIsProcessing(false);
      toast.error(err.message || "Upload error");
    } finally {
      setPendingFile(null);
    }
  };

  const searchCatalog = async (idx: number, q: string) => {
    setDrugQueryIdx(idx);
    if (q.trim().length < 2) {
      setDrugSearchResults([]);
      return;
    }
    try {
      const data = await apiFetch(`/api/drugs/search?q=${encodeURIComponent(q)}`);
      setDrugSearchResults(data.results || []);
    } catch {
      setDrugSearchResults([]);
    }
  };

  const applySuggestion = (idx: number, sug: any) => {
    setRxMeds((prev) =>
      prev.map((m, i) =>
        i === idx
          ? {
              ...m,
              raw_name: sug.brand_name,
              brand_name: sug.brand_name,
              generic_name: sug.generic_name,
              dosage: m.dosage || sug.strength,
              indicative_price_bdt: sug.indicative_price_bdt,
              confidence: sug.confidence || 1.0,
              confidence_tier: "auto_matched",
              needs_user_confirm: false,
            }
          : m
      )
    );
    setDrugQueryIdx(null);
    setDrugSearchResults([]);
  };

  const handleConfirmRx = async () => {
    if (!rxId) return;
    try {
      const res = await apiFetch(`/api/prescriptions/${rxId}/confirm`, {
        method: "POST",
        body: JSON.stringify({
          medicines: rxMeds.map((m) => ({
            name: m.raw_name || m.brand_name,
            dosage: m.dosage,
            frequency: m.frequency_bd,
            duration: m.duration,
            special_instructions: m.special_instructions,
          })),
        }),
      });
      setRxDdiAlerts(res.ddi_alerts || []);
      setHitlOpen(false);
      toast.success(
        res.ddi_alerts?.length
          ? `Saved with ${res.ddi_alerts.length} Drug Interaction/Duplicate Alert(s)!`
          : "Prescription confirmed and saved to vault!"
      );
    } catch (err: any) {
      toast.error(err.message || "Confirmation failed");
    }
  };

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold">Upload BD Prescriptions &amp; Lab Reports</h1>
        <p className="text-sm text-muted-foreground">
          DGDA Brand→Generic verification, duplicate PPI/NSAID safety alerts, and <code>mmol/L</code> LOINC normalization for{" "}
          <strong>{activeProfile?.display_name}</strong>
        </p>
      </div>

      {/* Upload / Camera Dropzone */}
      <Card className="p-8 border-2 border-dashed flex flex-col items-center text-center space-y-4">
        <div className="rounded-full bg-primary/10 p-5">
          <UploadIcon className="h-9 w-9 text-primary" />
        </div>
        <div>
          <h3 className="font-semibold text-lg">Take Photo or Upload Prescription / Lab PDF</h3>
          <p className="text-xs text-muted-foreground mt-1">Supports handwritten BD chamber pads &amp; Popular/Labaid/Ibn Sina PDFs</p>
        </div>
        <div className="flex flex-wrap gap-3 justify-center">
          <label className="cursor-pointer">
            <input
              type="file"
              accept="image/*,.pdf"
              className="hidden"
              disabled={isProcessing}
              onChange={(e) => onFileSelected(e.target.files?.[0])}
            />
            <Button type="button" asChild disabled={isProcessing}>
              <span><FileText className="h-4 w-4 mr-2" /> Choose File / PDF</span>
            </Button>
          </label>
          <label className="cursor-pointer">
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              disabled={isProcessing}
              onChange={(e) => onFileSelected(e.target.files?.[0])}
            />
            <Button type="button" variant="outline" asChild disabled={isProcessing}>
              <span><Camera className="h-4 w-4 mr-2" /> Capture Photo</span>
            </Button>
          </label>
        </div>
      </Card>

      {/* Async SSE Job Progress */}
      {jobState && (isProcessing || jobState.status === "failed") && (
        <Card className="p-4 space-y-2">
          <div className="flex items-center justify-between text-sm font-medium">
            <span className="flex items-center gap-2">
              {isProcessing && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
              {jobState.current_step}
            </span>
            <span>{jobState.progress_pct}%</span>
          </div>
          <Progress value={jobState.progress_pct} />
        </Card>
      )}

      {/* Lab Result Summary Card */}
      {labResult && (
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-lg flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                {labResult.lab_name || "Normalized Lab Report"}
              </h3>
              <p className="text-xs text-muted-foreground">Date: {labResult.report_date || "Recent"}</p>
            </div>
            <Badge>{labResult.normalized_metrics?.length || 0} Normalized Metrics</Badge>
          </div>
          {labResult.critical_alerts?.length > 0 && (
            <div className="rounded-lg border border-red-400 bg-red-50 p-3 text-xs text-red-900 space-y-1">
              {labResult.critical_alerts.map((a: any, i: number) => (
                <div key={i}><strong>CRITICAL: {a.title}</strong> — {a.action}</div>
              ))}
            </div>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {(labResult.normalized_metrics || []).map((m: any, idx: number) => (
              <div key={idx} className="rounded border p-2.5 flex items-center justify-between text-sm">
                <div>
                  <div className="font-medium">{m.canonical_name}</div>
                  <div className="text-[11px] text-muted-foreground">Ref: {m.reference_range || "N/A"}</div>
                </div>
                <div className="text-right">
                  <div className="font-bold">{m.canonical_value} {m.canonical_unit}</div>
                  <Badge variant={m.flag === "normal" ? "outline" : "destructive"} className="text-[10px] uppercase">
                    {m.flag}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Classification Modal */}
      <Dialog open={showTypeDialog} onOpenChange={setShowTypeDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Classify Medical Document</DialogTitle>
            <DialogDescription>{pendingFile?.name}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <Button variant="outline" className="h-auto py-4 justify-start text-left" onClick={() => handleUpload("prescription")}>
              <div>
                <div className="font-semibold">Doctor Prescription (Handwritten / Printed)</div>
                <div className="text-xs text-muted-foreground">Extracts medicines, 1+0+1 schedules &amp; runs DGDA DDI checks</div>
              </div>
            </Button>
            <Button variant="outline" className="h-auto py-4 justify-start text-left" onClick={() => handleUpload("lab_report")}>
              <div>
                <div className="font-semibold">Diagnostic Lab Report (CBC, HbA1c, Creatinine, Lipids)</div>
                <div className="text-xs text-muted-foreground">Normalizes mmol/L ↔ mg/dL, calculates CKD-EPI eGFR &amp; red flags</div>
              </div>
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Human-in-the-Loop Prescription Verification Modal */}
      <Dialog open={hitlOpen} onOpenChange={setHitlOpen}>
        <DialogContent className="max-w-2xl max-h-[88vh] overflow-auto">
          <DialogHeader>
            <DialogTitle>Verify Extracted Bangladesh Medications</DialogTitle>
            <DialogDescription>
              Confirm amber/red low-confidence handwritten brands against the DGDA Bangladesh catalog before saving.
            </DialogDescription>
          </DialogHeader>

          {rxSummary && (
            <div className="rounded bg-muted p-2.5 text-xs text-slate-700">{rxSummary}</div>
          )}

          {rxDdiAlerts.length > 0 && (
            <div className="rounded-lg border border-amber-500 bg-amber-50 p-3 text-xs text-amber-950 space-y-1.5">
              <div className="font-bold flex items-center gap-1.5">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                Duplicate-Generic / Interaction Warning Detected
              </div>
              {rxDdiAlerts.map((a, i) => (
                <div key={i}>
                  <Badge variant="destructive" className="mr-1.5 text-[10px]">{a.rule_type}</Badge>
                  {a.clinical_note}
                </div>
              ))}
            </div>
          )}

          <div className="space-y-3">
            {rxMeds.map((m, idx) => (
              <Card key={idx} className="p-3 space-y-2 relative">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={m.confidence >= 0.85 ? "default" : m.confidence >= 0.6 ? "secondary" : "destructive"}
                      className="text-[10px]"
                    >
                      {m.confidence >= 0.85 ? "Verified" : m.confidence >= 0.6 ? "Review" : "Manual"} ({Math.round((m.confidence || 0) * 100)}%)
                    </Badge>
                    {m.generic_name && <span className="text-xs font-medium text-primary">{m.generic_name}</span>}
                    {m.indicative_price_bdt && (
                      <span className="text-[11px] text-muted-foreground">~৳{m.indicative_price_bdt}/unit</span>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setRxMeds((prev) => prev.filter((_, i) => i !== idx))}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <div className="relative">
                    <Input
                      value={m.raw_name}
                      onChange={(e) => {
                        const val = e.target.value;
                        setRxMeds((prev) => prev.map((x, i) => (i === idx ? { ...x, raw_name: val } : x)));
                        searchCatalog(idx, val);
                      }}
                      placeholder="BD Brand (e.g. Seclo)"
                    />
                    {drugQueryIdx === idx && drugSearchResults.length > 0 && (
                      <div className="absolute z-50 left-0 right-0 mt-1 rounded border bg-popover shadow-md max-h-40 overflow-auto text-xs">
                        {drugSearchResults.map((s, si) => (
                          <button
                            type="button"
                            key={si}
                            onClick={() => applySuggestion(idx, s)}
                            className="w-full text-left px-2.5 py-1.5 hover:bg-muted flex justify-between"
                          >
                            <span><strong>{s.brand_name}</strong> ({s.strength})</span>
                            <span className="text-muted-foreground">{s.generic_name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <Input
                    value={m.dosage}
                    onChange={(e) =>
                      setRxMeds((prev) => prev.map((x, i) => (i === idx ? { ...x, dosage: e.target.value } : x)))
                    }
                    placeholder="Dosage (20mg)"
                  />
                  <Input
                    value={m.frequency_bd}
                    onChange={(e) =>
                      setRxMeds((prev) => prev.map((x, i) => (i === idx ? { ...x, frequency_bd: e.target.value } : x)))
                    }
                    placeholder="BD Schedule (1+0+1)"
                  />
                </div>

                {m.needs_user_confirm && m.suggestions && m.suggestions.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[11px]">
                    <Search className="h-3 w-3 text-muted-foreground" />
                    <span className="text-muted-foreground">DGDA Suggestions:</span>
                    {m.suggestions.map((s, si) => (
                      <Button
                        key={si}
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-6 px-2 text-[11px]"
                        onClick={() => applySuggestion(idx, s)}
                      >
                        {s.brand_name} {s.strength} ({s.generic_name})
                      </Button>
                    ))}
                  </div>
                )}
              </Card>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setRxMeds((prev) => [
                  ...prev,
                  {
                    raw_name: "",
                    brand_name: "",
                    dosage: "",
                    frequency_bd: "1+0+1",
                    duration: "",
                    special_instructions: "",
                    confidence: 0,
                    confidence_tier: "red_manual",
                    needs_user_confirm: true,
                  },
                ])
              }
            >
              <Plus className="h-3.5 w-3.5 mr-1" /> Add Medicine Row
            </Button>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setHitlOpen(false)}>Review Later</Button>
            <Button onClick={handleConfirmRx}>Confirm &amp; Save to Vault</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
