import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  Bold,
  CalendarClock,
  CheckCircle2,
  Code,
  Eye,
  EyeOff,
  GripVertical,
  Heading3,
  History,
  Italic,
  List,
  Plus,
  Quote,
  RotateCcw,
  Save,
  ShieldCheck,
  Table,
  Trash2,
  UploadCloud,
  Users,
  X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { MarkdownView } from "./MarkdownView";
import { MermaidDiagram } from "./MermaidDiagram";
import { TeamMember } from "./TeamGrid";
import { toast } from "sonner";

export interface DocsSettings {
  visibility_mode: "force_on" | "force_off" | "schedule";
  is_currently_available: boolean;
  availability_reason: string;
  publish_start_at: string | null;
  publish_end_at: string | null;
  duration_hours: number | null;
  team_name: string;
  active_version_tag: string;
}

export interface DocsSection {
  id: number;
  slug: string;
  category: "pitch" | "technical";
  section_code?: string | null;
  title: string;
  subtitle?: string | null;
  sort_order: number;
  is_visible: boolean;
  content_markdown: string;
  draft_markdown?: string;
  mermaid_diagram?: string | null;
  draft_mermaid?: string | null;
  has_unpublished_changes?: boolean;
}

export interface DocsVersion {
  id: number;
  version_tag: string;
  summary: string;
  published_by?: string | null;
  created_at?: string | null;
}

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function DocsAdminPanel({
  onClose,
  onSynced,
}: {
  onClose: () => void;
  onSynced: () => void;
}) {
  const [tab, setTab] = useState<"access" | "sections" | "team" | "versions">("access");
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState<DocsSettings | null>(null);
  const [sections, setSections] = useState<DocsSection[]>([]);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [versions, setVersions] = useState<DocsVersion[]>([]);

  // Access form
  const [visMode, setVisMode] = useState<"force_on" | "force_off" | "schedule">("force_on");
  const [startLocal, setStartLocal] = useState("");
  const [endLocal, setEndLocal] = useState("");
  const [customHours, setCustomHours] = useState("72");
  const [teamName, setTeamName] = useState("Team MediTrackAI");

  // Section editor
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editSubtitle, setEditSubtitle] = useState("");
  const [editMarkdown, setEditMarkdown] = useState("");
  const [editMermaid, setEditMermaid] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [dragId, setDragId] = useState<number | null>(null);
  const textAreaRef = useRef<HTMLTextAreaElement | null>(null);

  // Add section form
  const [addingSec, setAddingSec] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newSlug, setNewSlug] = useState("");
  const [newCat, setNewCat] = useState<"pitch" | "technical">("technical");

  // Publish form
  const [publishSummary, setPublishSummary] = useState("Updated live pitch & technical docs");

  // Team form
  const [newMemberName, setNewMemberName] = useState("");
  const [newMemberRole, setNewMemberRole] = useState("");
  const [newMemberEmail, setNewMemberEmail] = useState("");
  const [newMemberAvatar, setNewMemberAvatar] = useState("");

  async function loadAdminState() {
    setLoading(true);
    try {
      const data = await apiFetch("/api/live-docs/admin/state");
      setSettings(data.settings);
      setVisMode(data.settings.visibility_mode);
      setStartLocal(toLocalInput(data.settings.publish_start_at));
      setEndLocal(toLocalInput(data.settings.publish_end_at));
      setTeamName(data.settings.team_name || "Team MediTrackAI");
      setSections(data.sections || []);
      setTeam(data.team || []);
      setVersions(data.versions || []);
      if (data.sections?.length && !selectedId) {
        selectSection(data.sections[0]);
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to load admin state");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAdminState();
  }, []);

  function selectSection(s: DocsSection) {
    setSelectedId(s.id);
    setEditTitle(s.title);
    setEditSubtitle(s.subtitle || "");
    setEditMarkdown(s.draft_markdown ?? s.content_markdown ?? "");
    setEditMermaid(s.draft_mermaid ?? s.mermaid_diagram ?? "");
  }

  function insertSnippet(before: string, after = "") {
    const el = textAreaRef.current;
    if (!el) {
      setEditMarkdown((m) => m + before + after);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = editMarkdown.slice(start, end) || "text";
    const updated = editMarkdown.slice(0, start) + before + selected + after + editMarkdown.slice(end);
    setEditMarkdown(updated);
  }

  async function saveSettings(overrideMode?: "force_on" | "force_off" | "schedule", durationHrs?: number) {
    try {
      const payload: any = {
        visibility_mode: overrideMode || visMode,
        team_name: teamName,
      };
      if (durationHrs) {
        payload.duration_hours = durationHrs;
        payload.apply_duration_now = true;
      } else {
        if (startLocal) payload.publish_start_at = new Date(startLocal).toISOString();
        if (endLocal) payload.publish_end_at = new Date(endLocal).toISOString();
      }
      const res = await apiFetch("/api/live-docs/admin/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setSettings(res.settings);
      setVisMode(res.settings.visibility_mode);
      setStartLocal(toLocalInput(res.settings.publish_start_at));
      setEndLocal(toLocalInput(res.settings.publish_end_at));
      toast.success(`Access updated: ${res.settings.availability_reason}`);
      onSynced();
    } catch (e: any) {
      toast.error(e.message || "Failed to save settings");
    }
  }

  async function saveDraft(publishNow = false) {
    if (!selectedId) return;
    try {
      await apiFetch(`/api/live-docs/admin/sections/${selectedId}`, {
        method: "PUT",
        body: JSON.stringify({
          title: editTitle,
          subtitle: editSubtitle,
          draft_markdown: editMarkdown,
          draft_mermaid: editMermaid,
          publish_immediately: publishNow,
        }),
      });
      toast.success(publishNow ? "Section saved & published live" : "Draft saved");
      await loadAdminState();
      onSynced();
    } catch (e: any) {
      toast.error(e.message || "Save failed");
    }
  }

  async function toggleSectionVisibility(s: DocsSection) {
    try {
      await apiFetch(`/api/live-docs/admin/sections/${s.id}`, {
        method: "PUT",
        body: JSON.stringify({ is_visible: !s.is_visible }),
      });
      await loadAdminState();
      onSynced();
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  async function reorderList(nextList: DocsSection[]) {
    setSections(nextList);
    try {
      await apiFetch("/api/live-docs/admin/sections/reorder", {
        method: "PUT",
        body: JSON.stringify({ ordered_ids: nextList.map((s) => s.id) }),
      });
      onSynced();
    } catch (e: any) {
      toast.error(e.message || "Reorder failed");
    }
  }

  function moveSection(index: number, delta: -1 | 1) {
    const target = index + delta;
    if (target < 0 || target >= sections.length) return;
    const copy = [...sections];
    const [moved] = copy.splice(index, 1);
    copy.splice(target, 0, moved);
    reorderList(copy);
  }

  function handleDrop(targetId: number) {
    if (dragId === null || dragId === targetId) return;
    const fromIdx = sections.findIndex((s) => s.id === dragId);
    const toIdx = sections.findIndex((s) => s.id === targetId);
    if (fromIdx < 0 || toIdx < 0) return;
    const copy = [...sections];
    const [moved] = copy.splice(fromIdx, 1);
    copy.splice(toIdx, 0, moved);
    setDragId(null);
    reorderList(copy);
  }

  async function handleCreateSection() {
    if (!newTitle.trim() || !newSlug.trim()) return;
    try {
      const res = await apiFetch("/api/live-docs/admin/sections", {
        method: "POST",
        body: JSON.stringify({
          slug: newSlug.trim(),
          title: newTitle.trim(),
          category: newCat,
          content_markdown: "## New Section\n\nAdd technical or pitch details here.",
        }),
      });
      setAddingSec(false);
      setNewTitle("");
      setNewSlug("");
      await loadAdminState();
      if (res.section) selectSection(res.section);
      onSynced();
      toast.success("Section created");
    } catch (e: any) {
      toast.error(e.message || "Failed to add section");
    }
  }

  async function handleDeleteSection(id: number) {
    try {
      await apiFetch(`/api/live-docs/admin/sections/${id}`, { method: "DELETE" });
      if (selectedId === id) setSelectedId(null);
      await loadAdminState();
      onSynced();
      toast.success("Section deleted");
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  async function handlePublishAll() {
    try {
      const res = await apiFetch("/api/live-docs/admin/publish", {
        method: "POST",
        body: JSON.stringify({ summary: publishSummary }),
      });
      toast.success(`Published version ${res.version_tag}`);
      await loadAdminState();
      onSynced();
    } catch (e: any) {
      toast.error(e.message || "Publish failed");
    }
  }

  async function handleRollback(versionId: number) {
    try {
      const res = await apiFetch(`/api/live-docs/admin/versions/${versionId}/rollback`, {
        method: "POST",
      });
      toast.success(`Rolled back to ${res.restored_version}`);
      await loadAdminState();
      onSynced();
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  async function handleAddMember() {
    if (!newMemberName.trim() || !newMemberRole.trim() || !newMemberEmail.trim()) return;
    try {
      await apiFetch("/api/live-docs/admin/team", {
        method: "POST",
        body: JSON.stringify({
          full_name: newMemberName,
          role_title: newMemberRole,
          email: newMemberEmail,
          avatar_url: newMemberAvatar,
          is_active: true,
        }),
      });
      setNewMemberName("");
      setNewMemberRole("");
      setNewMemberEmail("");
      setNewMemberAvatar("");
      await loadAdminState();
      onSynced();
      toast.success("Team member added");
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  async function handleDeleteMember(id: number) {
    try {
      await apiFetch(`/api/live-docs/admin/team/${id}`, { method: "DELETE" });
      await loadAdminState();
      onSynced();
      toast.success("Team member removed");
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-2 sm:p-4">
      <div className="w-full max-w-6xl h-[92vh] rounded-2xl border border-border bg-background shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-card px-4 py-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <div>
              <h2 className="text-sm font-bold text-foreground">Live /docs Admin Console & CMS</h2>
              <p className="text-[11px] text-muted-foreground">
                {settings?.availability_reason || "Loading..."} · Version {settings?.active_version_tag}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handlePublishAll}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90"
            >
              <UploadCloud className="h-3.5 w-3.5" />
              Publish All & Snapshot
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-border p-1.5 text-muted-foreground hover:bg-muted"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-border bg-muted/30 px-4 py-2 overflow-x-auto">
          {[
            { id: "access", label: "Access Control & Schedule", icon: CalendarClock },
            { id: "sections", label: "Sections & WYSIWYG Editor", icon: Code },
            { id: "team", label: "Team Showcase", icon: Users },
            { id: "versions", label: "Versions & Rollback", icon: History },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id as any)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium whitespace-nowrap ${
                tab === t.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              }`}
            >
              <t.icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">Loading admin workspace...</div>
          ) : tab === "access" ? (
            <div className="max-w-3xl space-y-5">
              <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                <h3 className="text-sm font-bold text-foreground">Instant Visibility Override</h3>
                <div className="flex flex-wrap gap-2">
                  {[
                    { mode: "force_on", label: "Visibility ON (Public Now)" },
                    { mode: "force_off", label: "Visibility OFF (403 Not Available)" },
                    { mode: "schedule", label: "Follow Scheduled Window" },
                  ].map((opt) => (
                    <button
                      key={opt.mode}
                      type="button"
                      onClick={() => saveSettings(opt.mode as any)}
                      className={`rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
                        visMode === opt.mode
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-background hover:bg-muted"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  Current public status:{" "}
                  <strong className={settings?.is_currently_available ? "text-emerald-600" : "text-rose-600"}>
                    {settings?.is_currently_available ? "PUBLICLY ACCESSIBLE" : "HIDDEN (403)"}
                  </strong>{" "}
                  — {settings?.availability_reason}
                </p>
              </div>

              <div className="rounded-xl border border-border bg-card p-4 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-bold text-foreground">Schedule Window (Default: June 10 00:00 → June 14 23:59)</h3>
                  <button
                    type="button"
                    onClick={() => {
                      setStartLocal("2026-06-10T00:00");
                      setEndLocal("2026-06-14T23:59");
                      setVisMode("schedule");
                    }}
                    className="text-xs font-medium text-primary hover:underline"
                  >
                    Preset Default (June 10–14)
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Start Date & Time</label>
                    <input
                      type="datetime-local"
                      value={startLocal}
                      onChange={(e) => setStartLocal(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">End Date & Time</label>
                    <input
                      type="datetime-local"
                      value={endLocal}
                      onChange={(e) => setEndLocal(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs"
                    />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => saveSettings("schedule")}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Apply Scheduled Window
                </button>
              </div>

              <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                <h3 className="text-sm font-bold text-foreground">Duration-Based Publishing (From Now)</h3>
                <div className="flex flex-wrap items-center gap-2">
                  {[24, 72, 168].map((hrs) => (
                    <button
                      key={hrs}
                      type="button"
                      onClick={() => saveSettings("schedule", hrs)}
                      className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted"
                    >
                      Open for {hrs === 168 ? "7 Days" : `${hrs} Hours`}
                    </button>
                  ))}
                  <div className="flex items-center gap-1.5">
                    <input
                      type="number"
                      min={1}
                      value={customHours}
                      onChange={(e) => setCustomHours(e.target.value)}
                      className="w-20 rounded-lg border border-border bg-background px-2 py-1.5 text-xs"
                    />
                    <button
                      type="button"
                      onClick={() => saveSettings("schedule", Math.max(1, Number(customHours) || 24))}
                      className="rounded-lg border border-primary/40 bg-primary/10 px-2.5 py-1.5 text-xs font-semibold text-primary"
                    >
                      Publish N Hours
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : tab === "sections" ? (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-full">
              {/* Section List w/ Drag & Drop */}
              <div className="lg:col-span-4 space-y-2 border-r border-border pr-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase text-muted-foreground">Drag to Reorder ({sections.length})</span>
                  <button
                    type="button"
                    onClick={() => setAddingSec((v) => !v)}
                    className="inline-flex items-center gap-1 rounded bg-primary/10 px-2 py-1 text-xs font-semibold text-primary"
                  >
                    <Plus className="h-3.5 w-3.5" /> Add
                  </button>
                </div>

                {addingSec && (
                  <div className="rounded-lg border border-border bg-card p-2.5 space-y-2">
                    <input
                      placeholder="Title (e.g., Security Whitepaper)"
                      value={newTitle}
                      onChange={(e) => setNewTitle(e.target.value)}
                      className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                    />
                    <input
                      placeholder="Slug (e.g., custom-security)"
                      value={newSlug}
                      onChange={(e) => setNewSlug(e.target.value)}
                      className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                    />
                    <select
                      value={newCat}
                      onChange={(e) => setNewCat(e.target.value as any)}
                      className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
                    >
                      <option value="pitch">YC Pitch Deck</option>
                      <option value="technical">Technical Doc</option>
                    </select>
                    <button
                      type="button"
                      onClick={handleCreateSection}
                      className="w-full rounded bg-primary py-1 text-xs font-semibold text-primary-foreground"
                    >
                      Create Section
                    </button>
                  </div>
                )}

                <div className="space-y-1 max-h-[66vh] overflow-y-auto">
                  {sections.map((s, idx) => (
                    <div
                      key={s.id}
                      draggable
                      onDragStart={() => setDragId(s.id)}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => handleDrop(s.id)}
                      onClick={() => selectSection(s)}
                      className={`flex items-center justify-between gap-1.5 rounded-lg border px-2 py-1.5 cursor-pointer text-xs ${
                        selectedId === s.id ? "border-primary bg-primary/10" : "border-border bg-card hover:bg-muted/40"
                      }`}
                    >
                      <div className="flex items-center gap-1.5 min-w-0">
                        <GripVertical className="h-3.5 w-3.5 text-muted-foreground shrink-0 cursor-grab" />
                        <span className="rounded bg-muted px-1 font-mono text-[10px]">{s.section_code || s.category}</span>
                        <span className="truncate font-medium">{s.title}</span>
                        {s.has_unpublished_changes && <span className="h-2 w-2 rounded-full bg-amber-500 shrink-0" title="Unpublished draft" />}
                      </div>
                      <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                        <button type="button" onClick={() => moveSection(idx, -1)} className="p-0.5 hover:bg-muted rounded">
                          <ArrowUp className="h-3 w-3" />
                        </button>
                        <button type="button" onClick={() => moveSection(idx, 1)} className="p-0.5 hover:bg-muted rounded">
                          <ArrowDown className="h-3 w-3" />
                        </button>
                        <button type="button" onClick={() => toggleSectionVisibility(s)} className="p-0.5 hover:bg-muted rounded">
                          {s.is_visible ? <Eye className="h-3 w-3 text-emerald-600" /> : <EyeOff className="h-3 w-3 text-muted-foreground" />}
                        </button>
                        <button type="button" onClick={() => handleDeleteSection(s.id)} className="p-0.5 hover:bg-muted rounded text-rose-500">
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* WYSIWYG Editor */}
              <div className="lg:col-span-8 space-y-3">
                {selectedId ? (
                  <>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <input
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        placeholder="Section title"
                        className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm font-semibold"
                      />
                      <input
                        value={editSubtitle}
                        onChange={(e) => setEditSubtitle(e.target.value)}
                        placeholder="Subtitle"
                        className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs"
                      />
                    </div>

                    {/* WYSIWYG Toolbar */}
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted/40 px-2 py-1.5">
                      <div className="flex flex-wrap items-center gap-1">
                        <button type="button" onClick={() => insertSnippet("**", "**")} className="rounded p-1.5 hover:bg-muted" title="Bold">
                          <Bold className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => insertSnippet("*", "*")} className="rounded p-1.5 hover:bg-muted" title="Italic">
                          <Italic className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => insertSnippet("\n### ")} className="rounded p-1.5 hover:bg-muted" title="Heading">
                          <Heading3 className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => insertSnippet("\n- ")} className="rounded p-1.5 hover:bg-muted" title="Bullet List">
                          <List className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => insertSnippet("\n> ")} className="rounded p-1.5 hover:bg-muted" title="Quote">
                          <Quote className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => insertSnippet("`", "`")} className="rounded p-1.5 hover:bg-muted" title="Code">
                          <Code className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => insertSnippet("\n| Column A | Column B |\n| :--- | :--- |\n| Value 1 | Value 2 |\n")}
                          className="rounded p-1.5 hover:bg-muted"
                          title="Table"
                        >
                          <Table className="h-3.5 w-3.5" />
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowPreview((p) => !p)}
                        className="rounded-md border border-border bg-card px-2.5 py-1 text-xs font-medium"
                      >
                        {showPreview ? "Edit Source" : "Live Preview"}
                      </button>
                    </div>

                    {showPreview ? (
                      <div className="rounded-xl border border-border bg-card p-4 max-h-[45vh] overflow-y-auto">
                        <MarkdownView content={editMarkdown} />
                        {editMermaid.trim() && <MermaidDiagram code={editMermaid} />}
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <textarea
                          ref={textAreaRef}
                          rows={11}
                          value={editMarkdown}
                          onChange={(e) => setEditMarkdown(e.target.value)}
                          className="w-full rounded-xl border border-border bg-background p-3 font-mono text-xs leading-relaxed"
                        />
                        <div>
                          <label className="block text-[11px] font-semibold text-muted-foreground mb-1">
                            Optional Mermaid Diagram (Architecture / Flow)
                          </label>
                          <textarea
                            rows={4}
                            value={editMermaid}
                            onChange={(e) => setEditMermaid(e.target.value)}
                            placeholder="flowchart LR..."
                            className="w-full rounded-xl border border-border bg-background p-2.5 font-mono text-xs"
                          />
                        </div>
                      </div>
                    )}

                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => saveDraft(false)}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold hover:bg-muted"
                      >
                        <Save className="h-3.5 w-3.5" />
                        Save Draft
                      </button>
                      <button
                        type="button"
                        onClick={() => saveDraft(true)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
                      >
                        <UploadCloud className="h-3.5 w-3.5" />
                        Save & Publish Section
                      </button>
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">Select a section to edit.</p>
                )}
              </div>
            </div>
          ) : tab === "team" ? (
            <div className="max-w-4xl space-y-5">
              <div className="rounded-xl border border-border bg-card p-4 flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[200px]">
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Team Name</label>
                  <input
                    value={teamName}
                    onChange={(e) => setTeamName(e.target.value)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => saveSettings()}
                  className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground"
                >
                  Update Team Name
                </button>
              </div>

              <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                <h3 className="text-sm font-bold">Add Team Member</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                  <input
                    placeholder="Full Name"
                    value={newMemberName}
                    onChange={(e) => setNewMemberName(e.target.value)}
                    className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
                  />
                  <input
                    placeholder="Role in Application"
                    value={newMemberRole}
                    onChange={(e) => setNewMemberRole(e.target.value)}
                    className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
                  />
                  <input
                    placeholder="Email Address"
                    value={newMemberEmail}
                    onChange={(e) => setNewMemberEmail(e.target.value)}
                    className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
                  />
                  <input
                    placeholder="Profile Picture URL (optional)"
                    value={newMemberAvatar}
                    onChange={(e) => setNewMemberAvatar(e.target.value)}
                    className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleAddMember}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Member
                </button>
              </div>

              <div className="space-y-2">
                {team.map((m) => (
                  <div key={m.id} className="flex items-center justify-between rounded-xl border border-border bg-card px-4 py-2.5 text-xs">
                    <div>
                      <span className="font-bold text-foreground">{m.full_name}</span>
                      <span className="mx-2 text-muted-foreground">·</span>
                      <span className="text-primary font-medium">{m.role_title}</span>
                      <span className="mx-2 text-muted-foreground">·</span>
                      <span className="text-muted-foreground">{m.email}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteMember(m.id)}
                      className="rounded p-1 text-rose-500 hover:bg-muted"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl space-y-4">
              <div className="rounded-xl border border-border bg-card p-4 flex flex-wrap items-center gap-2">
                <input
                  value={publishSummary}
                  onChange={(e) => setPublishSummary(e.target.value)}
                  placeholder="Release note summary..."
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs"
                />
                <button
                  type="button"
                  onClick={handlePublishAll}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
                >
                  <UploadCloud className="h-3.5 w-3.5" /> Publish New Version
                </button>
              </div>

              <div className="space-y-2">
                {versions.map((v) => (
                  <div key={v.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-card px-4 py-3 text-xs">
                    <div>
                      <span className="rounded bg-primary/10 px-2 py-0.5 font-mono font-bold text-primary">{v.version_tag}</span>
                      <span className="ml-2 font-medium text-foreground">{v.summary}</span>
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        Published by {v.published_by || "admin"} · {v.created_at ? new Date(v.created_at).toLocaleString() : ""}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRollback(v.id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 text-xs font-medium hover:bg-muted"
                    >
                      <RotateCcw className="h-3.5 w-3.5" /> Rollback
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
