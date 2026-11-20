import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  BookOpen,
  Download,
  FileText,
  Lock,
  Presentation,
  Search,
  Settings2,
  Share2,
  ShieldAlert,
} from "lucide-react";
import { BACKEND_URL, getStoredToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { MarkdownView } from "@/components/docs/MarkdownView";
import { MermaidDiagram } from "@/components/docs/MermaidDiagram";
import { TeamGrid, TeamMember } from "@/components/docs/TeamGrid";
import { LiveMetricsPanel, LiveStats } from "@/components/docs/LiveMetricsPanel";
import { DocsAdminPanel, DocsSection, DocsSettings } from "@/components/docs/DocsAdminPanel";
import { toast } from "sonner";

interface PublicDocsResponse {
  available: boolean;
  is_admin: boolean;
  settings: DocsSettings;
  sections: DocsSection[];
  team: TeamMember[];
  live_stats: LiveStats;
}

export default function Docs() {
  const { user } = useAuth();
  const [data, setData] = useState<PublicDocsResponse | null>(null);
  const [blocked, setBlocked] = useState<{ reason: string; is_admin?: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshingStats, setRefreshingStats] = useState(false);

  const [modeFilter, setModeFilter] = useState<"all" | "pitch" | "technical" | "live">("all");
  const [search, setSearch] = useState("");
  const [adminOpen, setAdminOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const isAdmin = Boolean(data?.is_admin || blocked?.is_admin || user?.role === "admin" || user?.role === "super_admin");

  async function loadPublicDocs() {
    setLoading(true);
    try {
      const token = getStoredToken();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(`${BACKEND_URL}/api/live-docs/public`, { headers });
      const json = await res.json();
      if (res.status === 403) {
        const detail = json.detail || json;
        setBlocked({
          reason: detail.reason || "Documentation is not publicly available at this time.",
          is_admin: Boolean(detail.is_admin),
        });
        setData(null);
      } else if (res.ok) {
        setData(json);
        setBlocked(null);
      } else {
        throw new Error(json.detail || "Unable to load documentation");
      }
    } catch (e: any) {
      toast.error(e.message || "Error loading /docs");
    } finally {
      setLoading(false);
    }
  }

  async function refreshLiveStats() {
    if (!data) return;
    setRefreshingStats(true);
    try {
      const token = getStoredToken();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(`${BACKEND_URL}/api/live-docs/live-stats`, { headers });
      if (res.ok) {
        const stats = await res.json();
        setData((prev) => (prev ? { ...prev, live_stats: stats } : prev));
      }
    } finally {
      setRefreshingStats(false);
    }
  }

  useEffect(() => {
    loadPublicDocs();
  }, [user?.id]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const filteredSections = useMemo(() => {
    const secs = data?.sections || [];
    return secs.filter((s) => {
      if (modeFilter === "pitch" && s.category !== "pitch") return false;
      if (modeFilter === "technical" && s.category !== "technical") return false;
      if (modeFilter === "live") return false;
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        s.title.toLowerCase().includes(q) ||
        (s.subtitle || "").toLowerCase().includes(q) ||
        (s.content_markdown || "").toLowerCase().includes(q)
      );
    });
  }, [data?.sections, modeFilter, search]);

  async function handleExport(kind: "markdown" | "pdf") {
    try {
      const token = getStoredToken();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(`${BACKEND_URL}/api/live-docs/export/${kind}`, { headers });
      if (!res.ok) throw new Error("Export unavailable");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = kind === "pdf" ? "MediTrackAI-Live-Docs.pdf" : "MediTrackAI-Live-Docs.md";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toast.error(e.message || "Export failed");
    }
  }

  function handleCopyShareLink(slug?: string) {
    const url = `${window.location.origin}/docs${slug ? `#${slug}` : ""}`;
    navigator.clipboard.writeText(url);
    toast.success("Shareable link copied");
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-sm text-muted-foreground">
        Loading MediTrackAI Live Pitch Deck & Technical Docs...
      </div>
    );
  }

  if (blocked) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background px-4 text-center">
        <div className="max-w-md rounded-2xl border border-border bg-card p-8 shadow-sm space-y-4">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/10 text-rose-600">
            <Lock className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold text-foreground">Documentation Not Available (403)</h1>
          <p className="text-sm text-muted-foreground">{blocked.reason}</p>
          <div className="flex flex-wrap justify-center gap-2 pt-2">
            {isAdmin ? (
              <button
                type="button"
                onClick={() => setAdminOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground"
              >
                <Settings2 className="h-4 w-4" />
                Open Admin Visibility Controls
              </button>
            ) : (
              <Link
                to="/login"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-4 py-2 text-xs font-semibold hover:bg-muted"
              >
                Admin Sign In
              </Link>
            )}
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-muted"
            >
              Back to App
            </Link>
          </div>
        </div>
        {adminOpen && <DocsAdminPanel onClose={() => setAdminOpen(false)} onSynced={loadPublicDocs} />}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="min-h-screen bg-slate-50/60 dark:bg-background text-foreground">
      {/* Top Sticky Bar */}
      <header className="sticky top-0 z-30 border-b border-border bg-card/95 backdrop-blur print:hidden">
        <div className="mx-auto max-w-7xl px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Activity className="h-4 w-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold">MediTrackAI</span>
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-primary">
                    {data.settings.active_version_tag}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground">YC Pitch Deck + Live Technical Whitepaper</p>
              </div>
            </Link>
          </div>

          {/* Search */}
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              ref={searchInputRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search pitch, AI, APIs, security... (Ctrl+K)"
              className="w-full rounded-lg border border-border bg-background pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => handleExport("markdown")}
              className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
            >
              <Download className="h-3.5 w-3.5" /> .MD
            </button>
            <button
              type="button"
              onClick={() => handleExport("pdf")}
              className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
            >
              <FileText className="h-3.5 w-3.5" /> PDF
            </button>
            <button
              type="button"
              onClick={() => handleCopyShareLink()}
              className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
            >
              <Share2 className="h-3.5 w-3.5" /> Share
            </button>
            {isAdmin && (
              <button
                type="button"
                onClick={() => setAdminOpen(true)}
                className="inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90"
              >
                <Settings2 className="h-3.5 w-3.5" /> Admin CMS
              </button>
            )}
          </div>
        </div>

        {/* Mode Switcher */}
        <div className="mx-auto max-w-7xl px-4 pb-2.5 flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-1.5 overflow-x-auto">
            {[
              { id: "all", label: "Complete Dossier", icon: BookOpen },
              { id: "pitch", label: "YC Pitch Deck (12 Slides)", icon: Presentation },
              { id: "technical", label: "Technical Whitepaper (B–O)", icon: FileText },
              { id: "live", label: "Live System Dashboard", icon: Activity },
            ].map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setModeFilter(m.id as any)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition-colors ${
                  modeFilter === m.id
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted/70 text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <m.icon className="h-3.5 w-3.5" />
                {m.label}
              </button>
            ))}
          </div>
          <span className="text-[11px] text-emerald-700 bg-emerald-500/10 px-2.5 py-0.5 rounded-full font-medium">
            {data.settings.availability_reason}
          </span>
        </div>
      </header>

      {/* Main Content */}
      <div className="mx-auto max-w-7xl px-4 py-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Sticky Sidebar TOC */}
        <aside className="hidden lg:block lg:col-span-3 print:hidden">
          <div className="sticky top-28 rounded-xl border border-border bg-card p-3 max-h-[78vh] overflow-y-auto space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground px-1">
              Section Navigation
            </div>
            <nav className="space-y-0.5">
              {(data.sections || []).map((s) => (
                <a
                  key={s.id}
                  href={`#${s.slug}`}
                  onClick={() => {
                    if (modeFilter === "live") setModeFilter("all");
                  }}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <span className="font-mono text-[10px] font-semibold text-primary w-10 shrink-0">
                    {s.section_code || s.category.toUpperCase()}
                  </span>
                  <span className="truncate">{s.title}</span>
                </a>
              ))}
              <a
                href="#live-system-dashboard"
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-500/10"
              >
                <span className="font-mono text-[10px] w-10 shrink-0">LIVE</span>
                <span>System State & APIs</span>
              </a>
            </nav>
          </div>
        </aside>

        {/* Document Stream */}
        <main className="lg:col-span-9 space-y-6">
          {/* Hero Summary Banner */}
          <section className="rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/10 via-card to-card p-6 shadow-sm">
            <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-primary">
              <ShieldAlert className="h-4 w-4" />
              <span>Neuro-Symbolic Bangladesh Clinical Memory Platform · {data.settings.team_name}</span>
            </div>
            <h1 className="mt-2 text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
              MediTrackAI — Pitch Deck & Live Technical Documentation
            </h1>
            <p className="mt-2 text-sm text-muted-foreground max-w-3xl">
              Speak in Bangla or Banglish; verify deterministically against Bangladesh DGDA brands, LOINC unit
              conversions, and emergency red-flag gates; deliver a verifiable 1-page English Doctor Brief via QR.
            </p>
          </section>

          {/* Sections */}
          {filteredSections.map((sec) => (
            <section
              key={sec.id}
              id={sec.slug}
              className="scroll-mt-32 rounded-2xl border border-border bg-card p-5 sm:p-6 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border pb-3 mb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded px-2 py-0.5 font-mono text-[11px] font-bold ${
                        sec.category === "pitch"
                          ? "bg-amber-500/15 text-amber-700"
                          : "bg-primary/10 text-primary"
                      }`}
                    >
                      {sec.section_code || (sec.category === "pitch" ? "YC" : "TECH")}
                    </span>
                    <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
                      {sec.category === "pitch" ? "YC Pitch Slide" : "Technical Architecture"}
                    </span>
                  </div>
                  <h2 className="mt-1.5 text-xl font-bold text-foreground">{sec.title}</h2>
                  {sec.subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{sec.subtitle}</p>}
                </div>
                <button
                  type="button"
                  onClick={() => handleCopyShareLink(sec.slug)}
                  className="rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted print:hidden"
                >
                  #{sec.slug}
                </button>
              </div>

              <MarkdownView content={sec.content_markdown} />

              {sec.mermaid_diagram && <MermaidDiagram code={sec.mermaid_diagram} />}

              {(sec.slug === "yc-team" || sec.slug === "tech-team") && (
                <TeamGrid teamName={data.settings.team_name} members={data.team} />
              )}
            </section>
          ))}

          {/* Live System State & Auto-Synced API Explorer */}
          <section
            id="live-system-dashboard"
            className="scroll-mt-32 rounded-2xl border border-emerald-500/30 bg-card p-5 sm:p-6 shadow-sm"
          >
            <LiveMetricsPanel
              stats={data.live_stats}
              onRefresh={refreshLiveStats}
              refreshing={refreshingStats}
            />
          </section>
        </main>
      </div>

      {adminOpen && <DocsAdminPanel onClose={() => setAdminOpen(false)} onSynced={loadPublicDocs} />}
    </div>
  );
}
