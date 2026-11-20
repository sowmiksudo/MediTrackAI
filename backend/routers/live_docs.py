from datetime import datetime, timedelta, timezone
import html
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ai_core.config import get_settings
from ai_core.router import TELEMETRY_STORE, get_ai_provider
from auth.dependencies import get_optional_user, require_admin_user
from db.database import get_db
from db.models import (
    BackgroundJob,
    BdDdiRule,
    BdDrugCatalog,
    CheckIn,
    DoctorBrief,
    KnowledgeChunk,
    LiveDocsSection,
    LiveDocsSettings,
    LiveDocsTeamMember,
    LiveDocsVersion,
    LoincLabReference,
    PatientProfile,
    Prescription,
    Report,
    User,
)
from seeds.seed_live_docs import ensure_live_docs_seeded

router = APIRouter(prefix="/api/live-docs", tags=["live-docs"])


def _evaluate_visibility(settings: LiveDocsSettings, now: Optional[datetime] = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc)
    mode = (settings.visibility_mode or "force_on").lower()
    if mode == "force_on":
        return True, "Publicly enabled (Instant Admin Override)"
    if mode == "force_off":
        return False, "Documentation is currently turned OFF by an administrator."

    # mode == "schedule"
    start = settings.publish_start_at
    end = settings.publish_end_at
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    if start and now < start:
        return False, f"Scheduled to open at {start.isoformat()}"
    if end and now > end:
        return False, f"Scheduled window ended at {end.isoformat()}"
    return True, "Publicly available within scheduled window"


def _collect_live_stats(db: Session, request: Optional[Request] = None) -> Dict[str, Any]:
    app_settings = get_settings()
    provider = get_ai_provider()
    counts = {
        "users": db.query(User).count(),
        "patient_profiles": db.query(PatientProfile).count(),
        "prescriptions": db.query(Prescription).count(),
        "lab_reports": db.query(Report).count(),
        "checkins": db.query(CheckIn).count(),
        "doctor_briefs": db.query(DoctorBrief).count(),
        "knowledge_chunks": db.query(KnowledgeChunk).count(),
        "bd_drugs": db.query(BdDrugCatalog).count(),
        "bd_ddi_rules": db.query(BdDdiRule).count(),
        "loinc_labs": db.query(LoincLabReference).count(),
        "background_jobs": db.query(BackgroundJob).count(),
    }

    routes: List[Dict[str, Any]] = []
    if request is not None:
        for r in request.app.routes:
            if isinstance(r, APIRoute) and not r.path.startswith("/openapi"):
                methods = sorted(m for m in (r.methods or set()) if m not in ("HEAD", "OPTIONS"))
                routes.append(
                    {
                        "path": r.path,
                        "methods": methods,
                        "tags": list(r.tags or []),
                        "name": r.name,
                    }
                )
        routes.sort(key=lambda x: x["path"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inference_mode": app_settings.inference_mode,
        "provider_mode": provider.mode_name,
        "counts": counts,
        "telemetry": TELEMETRY_STORE.snapshot(),
        "api_routes": routes,
    }


def _serialize_settings(s: LiveDocsSettings) -> Dict[str, Any]:
    available, reason = _evaluate_visibility(s)
    return {
        "visibility_mode": s.visibility_mode,
        "is_currently_available": available,
        "availability_reason": reason,
        "publish_start_at": s.publish_start_at.isoformat() if s.publish_start_at else None,
        "publish_end_at": s.publish_end_at.isoformat() if s.publish_end_at else None,
        "duration_hours": s.duration_hours,
        "team_name": s.team_name,
        "active_version_tag": s.active_version_tag,
        "updated_by": s.updated_by,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_section(s: LiveDocsSection, include_draft: bool = False) -> Dict[str, Any]:
    data = {
        "id": s.id,
        "slug": s.slug,
        "category": s.category,
        "section_code": s.section_code,
        "title": s.title,
        "subtitle": s.subtitle,
        "sort_order": s.sort_order,
        "is_visible": s.is_visible,
        "content_markdown": s.content_markdown,
        "mermaid_diagram": s.mermaid_diagram,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
    if include_draft:
        data["draft_markdown"] = s.draft_markdown
        data["draft_mermaid"] = s.draft_mermaid
        data["has_unpublished_changes"] = s.has_unpublished_changes
    return data


def _serialize_team(t: LiveDocsTeamMember) -> Dict[str, Any]:
    return {
        "id": t.id,
        "full_name": t.full_name,
        "role_title": t.role_title,
        "email": t.email,
        "avatar_url": t.avatar_url or "",
        "sort_order": t.sort_order,
        "is_active": t.is_active,
    }


def _ensure_seeded(db: Session) -> LiveDocsSettings:
    ensure_live_docs_seeded(db)
    return db.query(LiveDocsSettings).filter(LiveDocsSettings.id == 1).first()


# -------------------- PUBLIC ENDPOINTS --------------------


@router.get("/public")
def get_public_docs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    settings = _ensure_seeded(db)
    available, reason = _evaluate_visibility(settings)
    is_admin = bool(current_user and (getattr(current_user, "role", "user") in ("admin", "super_admin")))

    if not available:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "available": False,
                "reason": reason,
                "visibility_mode": settings.visibility_mode,
                "publish_start_at": settings.publish_start_at.isoformat() if settings.publish_start_at else None,
                "publish_end_at": settings.publish_end_at.isoformat() if settings.publish_end_at else None,
                "is_admin": is_admin,
            },
        )

    sections = (
        db.query(LiveDocsSection)
        .filter(LiveDocsSection.is_visible == True)
        .order_by(LiveDocsSection.sort_order.asc(), LiveDocsSection.id.asc())
        .all()
    )
    team = (
        db.query(LiveDocsTeamMember)
        .filter(LiveDocsTeamMember.is_active == True)
        .order_by(LiveDocsTeamMember.sort_order.asc(), LiveDocsTeamMember.id.asc())
        .all()
    )
    versions = db.query(LiveDocsVersion).order_by(desc(LiveDocsVersion.created_at)).limit(10).all()

    return {
        "available": True,
        "is_admin": is_admin,
        "settings": _serialize_settings(settings),
        "sections": [_serialize_section(s, include_draft=False) for s in sections],
        "team": [_serialize_team(t) for t in team],
        "versions": [
            {
                "id": v.id,
                "version_tag": v.version_tag,
                "summary": v.summary,
                "published_by": v.published_by,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
        "live_stats": _collect_live_stats(db, request),
    }


@router.get("/live-stats")
def get_live_stats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    settings = _ensure_seeded(db)
    available, reason = _evaluate_visibility(settings)
    is_admin = bool(current_user and (getattr(current_user, "role", "user") in ("admin", "super_admin")))
    if not available and not is_admin:
        raise HTTPException(status_code=403, detail={"available": False, "reason": reason})
    return _collect_live_stats(db, request)


def _assemble_markdown(settings: LiveDocsSettings, sections: List[LiveDocsSection], team: List[LiveDocsTeamMember], stats: Dict[str, Any]) -> str:
    lines = [
        f"# MediTrackAI — Live Pitch Deck & Technical Documentation ({settings.active_version_tag})",
        "",
        f"> **Team:** {settings.team_name}  ",
        f"> **Active Inference Mode:** `{stats['inference_mode']}` | **Generated:** {stats['generated_at']}",
        "",
        "## Live System Snapshot",
        "",
    ]
    for k, v in stats["counts"].items():
        lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
    lines.append("")

    for sec in sections:
        prefix = f"[{sec.section_code}] " if sec.section_code else ""
        lines.append(f"## {prefix}{sec.title}")
        if sec.subtitle:
            lines.append(f"*{sec.subtitle}*")
        lines.append("")
        lines.append(sec.content_markdown or "")
        if sec.mermaid_diagram:
            lines.append("")
            lines.append("```mermaid")
            lines.append(sec.mermaid_diagram)
            lines.append("```")
        if sec.slug in ("yc-team", "tech-team") and team:
            lines.append("")
            lines.append(f"### {settings.team_name} Directory")
            for m in team:
                lines.append(f"- **{m.full_name}** — {m.role_title} ({m.email})")
        lines.append("")
    return "\n".join(lines)


@router.get("/export/markdown")
def export_markdown(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    settings = _ensure_seeded(db)
    available, reason = _evaluate_visibility(settings)
    is_admin = bool(current_user and (getattr(current_user, "role", "user") in ("admin", "super_admin")))
    if not available and not is_admin:
        raise HTTPException(status_code=403, detail={"available": False, "reason": reason})

    sections = (
        db.query(LiveDocsSection)
        .filter(LiveDocsSection.is_visible == True)
        .order_by(LiveDocsSection.sort_order.asc())
        .all()
    )
    team = (
        db.query(LiveDocsTeamMember)
        .filter(LiveDocsTeamMember.is_active == True)
        .order_by(LiveDocsTeamMember.sort_order.asc())
        .all()
    )
    stats = _collect_live_stats(db, request)
    md = _assemble_markdown(settings, sections, team, stats)
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="MediTrackAI-Live-Docs.md"'},
    )


@router.get("/export/pdf")
def export_pdf(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    from weasyprint import HTML

    settings = _ensure_seeded(db)
    available, reason = _evaluate_visibility(settings)
    is_admin = bool(current_user and (getattr(current_user, "role", "user") in ("admin", "super_admin")))
    if not available and not is_admin:
        raise HTTPException(status_code=403, detail={"available": False, "reason": reason})

    sections = (
        db.query(LiveDocsSection)
        .filter(LiveDocsSection.is_visible == True)
        .order_by(LiveDocsSection.sort_order.asc())
        .all()
    )
    team = (
        db.query(LiveDocsTeamMember)
        .filter(LiveDocsTeamMember.is_active == True)
        .order_by(LiveDocsTeamMember.sort_order.asc())
        .all()
    )
    stats = _collect_live_stats(db, request)

    cards_html = "".join(
        f"""
        <div class="sec">
          <div class="badge">{html.escape(s.section_code or s.category.upper())}</div>
          <h2>{html.escape(s.title)}</h2>
          <p class="sub">{html.escape(s.subtitle or '')}</p>
          <pre class="md">{html.escape(s.content_markdown or '')}</pre>
        </div>
        """
        for s in sections
    )
    team_html = "".join(
        f"<tr><td>{html.escape(m.full_name)}</td><td>{html.escape(m.role_title)}</td><td>{html.escape(m.email)}</td></tr>"
        for m in team
    )
    counts = stats["counts"]
    html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  @page {{ size: A4; margin: 14mm; }}
  body {{ font-family: Arial, sans-serif; color: #0f172a; font-size: 10pt; line-height: 1.45; }}
  h1 {{ color: #0f766e; margin-bottom: 4px; font-size: 18pt; }}
  .meta {{ color: #475569; font-size: 9pt; margin-bottom: 14px; border-bottom: 2px solid #0f766e; padding-bottom: 8px; }}
  .stats {{ background: #f0fdfa; border: 1px solid #99f6e4; padding: 8px 12px; border-radius: 6px; margin-bottom: 14px; font-size: 9pt; }}
  .sec {{ margin-bottom: 14px; page-break-inside: avoid; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; }}
  .badge {{ display: inline-block; background: #0f766e; color: #fff; font-size: 8pt; font-weight: bold; padding: 2px 6px; border-radius: 4px; margin-bottom: 4px; }}
  h2 {{ margin: 2px 0; font-size: 12pt; color: #0f172a; }}
  .sub {{ margin: 0 0 6px 0; color: #64748b; font-size: 9pt; font-style: italic; }}
  .md {{ white-space: pre-wrap; font-family: Arial, sans-serif; margin: 0; font-size: 9.5pt; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 9pt; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 5px 8px; text-align: left; }}
  th {{ background: #f1f5f9; }}
</style>
</head>
<body>
  <h1>MediTrackAI — Live Pitch Deck & Technical Dossier</h1>
  <div class="meta">Version {html.escape(settings.active_version_tag)} · {html.escape(settings.team_name)} · Mode: {html.escape(stats['inference_mode'])}</div>
  <div class="stats">
    <strong>Live System State:</strong>
    Profiles: {counts['patient_profiles']} | Prescriptions: {counts['prescriptions']} | Lab Reports: {counts['lab_reports']} |
    Check-Ins: {counts['checkins']} | Doctor Briefs: {counts['doctor_briefs']} | RAG Chunks: {counts['knowledge_chunks']} |
    BD Drugs: {counts['bd_drugs']} | API Routes: {len(stats['api_routes'])}
  </div>
  {cards_html}
  <div class="sec">
    <h2>{html.escape(settings.team_name)}</h2>
    <table>
      <thead><tr><th>Name</th><th>Role</th><th>Email</th></tr></thead>
      <tbody>{team_html}</tbody>
    </table>
  </div>
</body>
</html>"""
    pdf_bytes = HTML(string=html_doc).write_pdf()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="MediTrackAI-Live-Docs.pdf"'},
    )


# -------------------- ADMIN ENDPOINTS (PROTECTED) --------------------


class SettingsUpdate(BaseModel):
    visibility_mode: Optional[str] = Field(default=None, pattern="^(force_on|force_off|schedule)$")
    publish_start_at: Optional[datetime] = None
    publish_end_at: Optional[datetime] = None
    duration_hours: Optional[int] = Field(default=None, ge=1, le=8760)
    apply_duration_now: bool = False
    team_name: Optional[str] = Field(default=None, min_length=2, max_length=160)


class SectionCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=80)
    category: str = Field(default="technical", pattern="^(pitch|technical)$")
    section_code: Optional[str] = Field(default=None, max_length=16)
    title: str = Field(..., min_length=1, max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    content_markdown: str = ""
    mermaid_diagram: Optional[str] = None
    is_visible: bool = True


class SectionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    category: Optional[str] = Field(default=None, pattern="^(pitch|technical)$")
    section_code: Optional[str] = Field(default=None, max_length=16)
    is_visible: Optional[bool] = None
    draft_markdown: Optional[str] = None
    draft_mermaid: Optional[str] = None
    publish_immediately: bool = False


class ReorderRequest(BaseModel):
    ordered_ids: List[int]


class PublishRequest(BaseModel):
    version_tag: Optional[str] = Field(default=None, max_length=48)
    summary: str = Field(default="Published live documentation update", max_length=300)


class TeamMemberPayload(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=160)
    role_title: str = Field(..., min_length=1, max_length=160)
    email: str = Field(..., min_length=3, max_length=255)
    avatar_url: Optional[str] = ""
    is_active: bool = True


@router.get("/admin/state")
def get_admin_state(
    request: Request,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    settings = _ensure_seeded(db)
    sections = db.query(LiveDocsSection).order_by(LiveDocsSection.sort_order.asc(), LiveDocsSection.id.asc()).all()
    team = db.query(LiveDocsTeamMember).order_by(LiveDocsTeamMember.sort_order.asc(), LiveDocsTeamMember.id.asc()).all()
    versions = db.query(LiveDocsVersion).order_by(desc(LiveDocsVersion.created_at)).limit(20).all()
    return {
        "settings": _serialize_settings(settings),
        "sections": [_serialize_section(s, include_draft=True) for s in sections],
        "team": [_serialize_team(t) for t in team],
        "versions": [
            {
                "id": v.id,
                "version_tag": v.version_tag,
                "summary": v.summary,
                "published_by": v.published_by,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
        "live_stats": _collect_live_stats(db, request),
    }


@router.put("/admin/settings")
def update_settings(
    req: SettingsUpdate,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    settings = _ensure_seeded(db)
    if req.apply_duration_now and req.duration_hours:
        now = datetime.now(timezone.utc)
        settings.visibility_mode = "schedule"
        settings.publish_start_at = now
        settings.publish_end_at = now + timedelta(hours=req.duration_hours)
        settings.duration_hours = req.duration_hours
    else:
        if req.visibility_mode is not None:
            settings.visibility_mode = req.visibility_mode
        if req.publish_start_at is not None:
            settings.publish_start_at = req.publish_start_at
        if req.publish_end_at is not None:
            settings.publish_end_at = req.publish_end_at
        if req.duration_hours is not None:
            settings.duration_hours = req.duration_hours
    if req.team_name is not None:
        settings.team_name = req.team_name.strip()
    settings.updated_by = admin.email or str(admin.id)
    db.commit()
    db.refresh(settings)
    return {"success": True, "settings": _serialize_settings(settings)}


@router.post("/admin/sections", status_code=status.HTTP_201_CREATED)
def create_section(
    req: SectionCreate,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    _ensure_seeded(db)
    slug_clean = req.slug.strip().lower().replace(" ", "-")
    if db.query(LiveDocsSection).filter(LiveDocsSection.slug == slug_clean).first():
        raise HTTPException(status_code=409, detail="Section slug already exists")
    max_order = db.query(LiveDocsSection).count()
    sec = LiveDocsSection(
        slug=slug_clean,
        category=req.category,
        section_code=req.section_code,
        title=req.title.strip(),
        subtitle=req.subtitle,
        sort_order=max_order,
        is_visible=req.is_visible,
        content_markdown=req.content_markdown,
        draft_markdown=req.content_markdown,
        mermaid_diagram=req.mermaid_diagram,
        draft_mermaid=req.mermaid_diagram,
        has_unpublished_changes=False,
    )
    db.add(sec)
    db.commit()
    db.refresh(sec)
    return {"success": True, "section": _serialize_section(sec, include_draft=True)}


@router.put("/admin/sections/reorder")
def reorder_sections(
    req: ReorderRequest,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    sections = {s.id: s for s in db.query(LiveDocsSection).all()}
    for idx, sid in enumerate(req.ordered_ids):
        if sid in sections:
            sections[sid].sort_order = idx
    db.commit()
    return {"success": True}


@router.put("/admin/sections/{section_id}")
def update_section(
    section_id: int,
    req: SectionUpdate,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    sec = db.query(LiveDocsSection).filter(LiveDocsSection.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    if req.title is not None:
        sec.title = req.title.strip()
    if req.subtitle is not None:
        sec.subtitle = req.subtitle
    if req.category is not None:
        sec.category = req.category
    if req.section_code is not None:
        sec.section_code = req.section_code
    if req.is_visible is not None:
        sec.is_visible = req.is_visible
    if req.draft_markdown is not None:
        sec.draft_markdown = req.draft_markdown
        sec.has_unpublished_changes = True
    if req.draft_mermaid is not None:
        sec.draft_mermaid = req.draft_mermaid
        sec.has_unpublished_changes = True

    if req.publish_immediately:
        sec.content_markdown = sec.draft_markdown
        sec.mermaid_diagram = sec.draft_mermaid
        sec.has_unpublished_changes = False

    db.commit()
    db.refresh(sec)
    return {"success": True, "section": _serialize_section(sec, include_draft=True)}


@router.delete("/admin/sections/{section_id}")
def delete_section(
    section_id: int,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    sec = db.query(LiveDocsSection).filter(LiveDocsSection.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    db.delete(sec)
    db.commit()
    return {"success": True}


@router.post("/admin/publish")
def publish_all_drafts(
    req: PublishRequest,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    settings = _ensure_seeded(db)
    sections = db.query(LiveDocsSection).order_by(LiveDocsSection.sort_order.asc()).all()
    for s in sections:
        s.content_markdown = s.draft_markdown
        s.mermaid_diagram = s.draft_mermaid
        s.has_unpublished_changes = False

    team = db.query(LiveDocsTeamMember).order_by(LiveDocsTeamMember.sort_order.asc()).all()
    if req.version_tag:
        tag = req.version_tag.strip()
    else:
        count = db.query(LiveDocsVersion).count()
        tag = f"v1.{count}.0"

    settings.active_version_tag = tag
    settings.updated_by = admin.email or str(admin.id)

    ver = LiveDocsVersion(
        version_tag=tag,
        summary=req.summary,
        published_by=admin.email or str(admin.id),
        snapshot_json={
            "team_name": settings.team_name,
            "sections": [
                {
                    "slug": s.slug,
                    "category": s.category,
                    "section_code": s.section_code,
                    "title": s.title,
                    "subtitle": s.subtitle,
                    "sort_order": s.sort_order,
                    "is_visible": s.is_visible,
                    "content_markdown": s.content_markdown,
                    "mermaid_diagram": s.mermaid_diagram,
                }
                for s in sections
            ],
            "team": [_serialize_team(t) for t in team],
        },
    )
    db.add(ver)
    db.commit()
    return {"success": True, "version_tag": tag, "version_id": ver.id}


@router.post("/admin/versions/{version_id}/rollback")
def rollback_version(
    version_id: int,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    settings = _ensure_seeded(db)
    ver = db.query(LiveDocsVersion).filter(LiveDocsVersion.id == version_id).first()
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found")

    snap = ver.snapshot_json or {}
    if snap.get("team_name"):
        settings.team_name = snap["team_name"]
    settings.active_version_tag = ver.version_tag

    existing_by_slug = {s.slug: s for s in db.query(LiveDocsSection).all()}
    for item in snap.get("sections", []):
        sec = existing_by_slug.get(item["slug"])
        if sec:
            sec.category = item.get("category", sec.category)
            sec.section_code = item.get("section_code")
            sec.title = item["title"]
            sec.subtitle = item.get("subtitle")
            sec.sort_order = item.get("sort_order", 0)
            sec.is_visible = item.get("is_visible", True)
            sec.content_markdown = item.get("content_markdown", "")
            sec.draft_markdown = item.get("content_markdown", "")
            sec.mermaid_diagram = item.get("mermaid_diagram")
            sec.draft_mermaid = item.get("mermaid_diagram")
            sec.has_unpublished_changes = False

    db.commit()
    return {"success": True, "restored_version": ver.version_tag}


@router.post("/admin/team", status_code=status.HTTP_201_CREATED)
def add_team_member(
    req: TeamMemberPayload,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    _ensure_seeded(db)
    order = db.query(LiveDocsTeamMember).count()
    member = LiveDocsTeamMember(
        full_name=req.full_name.strip(),
        role_title=req.role_title.strip(),
        email=req.email.strip(),
        avatar_url=(req.avatar_url or "").strip(),
        sort_order=order,
        is_active=req.is_active,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return {"success": True, "member": _serialize_team(member)}


@router.put("/admin/team/{member_id}")
def update_team_member(
    member_id: int,
    req: TeamMemberPayload,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    member = db.query(LiveDocsTeamMember).filter(LiveDocsTeamMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    member.full_name = req.full_name.strip()
    member.role_title = req.role_title.strip()
    member.email = req.email.strip()
    member.avatar_url = (req.avatar_url or "").strip()
    member.is_active = req.is_active
    db.commit()
    db.refresh(member)
    return {"success": True, "member": _serialize_team(member)}


@router.delete("/admin/team/{member_id}")
def delete_team_member(
    member_id: int,
    admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    member = db.query(LiveDocsTeamMember).filter(LiveDocsTeamMember.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    db.delete(member)
    db.commit()
    return {"success": True}
