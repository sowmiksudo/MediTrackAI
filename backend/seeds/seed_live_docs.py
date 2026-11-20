from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from db.models import (
    LiveDocsSection,
    LiveDocsSettings,
    LiveDocsTeamMember,
    LiveDocsVersion,
)

BD_TZ = timezone(timedelta(hours=6))


def _default_sections() -> List[Dict[str, Any]]:
    arch_mermaid = """flowchart TB
    U["Patient & NRB Caregiver PWA (React + TypeScript :3000)"] --> AUTH["Argon2 + PyJWT Auth & Profile Vault"]
    AUTH --> API["FastAPI Orchestrator (:8000) + Signed /uploads/"]
    U -->|"/ws/live PCM16 / Text"| WS["AdaptiveVad (Silero v5 / Noise-Floor RMS)"]
    U -->|"Rx & Lab Upload"| PIPE["Async Pipelines (rx_pipeline / lab_pipeline)"]
    WS --> ROUTER["3-Tier Split AI Router (cloud | hybrid_gpu)"]
    PIPE --> ROUTER
    ROUTER --> T0["Tier 0 Deterministic ($0): LOINC / CKD-EPI / BD Drugs / 999 Gate"]
    ROUTER --> T1["Tier 1 Local GPU: Whisper / BGE-M3 / Qwen3-Reranker / MedGemma 4B"]
    ROUTER --> T2["Tier 2 Cloud: gemini-3.1-flash-lite + gemini-3.8-flash + Bangla TTS"]
    T0 --> DB["PostgreSQL 16 + pgvector (:5433) — 15 Domain Tables"]
    T1 --> DB
    T2 --> DB
    DB --> RAG["3-Leg Hybrid RAG (HALFVEC + BM25 + pg_trgm -> RRF + Decay)"]
    RAG --> BRIEF["WeasyPrint 1-Page English Doctor Brief + 72h QR"]
    ROUTER -.-> TELE["Live TelemetryDrawer (Citations, PII Diff, Latency)"]"""

    dataflow_mermaid = """flowchart LR
    IN["1. Input: Bangla/Banglish Voice, Handwritten BD Rx, Mixed-Unit Lab PDF"] --> PRE["2. Pre-Gate: AdaptiveVad + Regex/MedGemma PHI Redaction + 999 Red-Flag Check"]
    PRE --> PROC["3. Split AI Processing: VLM Extraction + RapidFuzz BD Drugs + LOINC Unit Normalization"]
    PROC --> STORE["4. Longitudinal Memory: PostgreSQL Observations + MedicationEpisodes + Dual HALFVEC Chunks"]
    STORE --> RAG["5. Hybrid RAG + Reasoning: Banglish Expansion -> HNSW + BM25 + Trigram -> RRF + Reranker"]
    RAG --> OUT["6. Output: 1-Page English Doctor Brief PDF + 72h QR + Bangla Voice Reply"]
    OUT --> FB["7. Human-in-the-Loop Feedback: <0.85 Rx Confirm + Clinical Audit + Telemetry Trace"]"""

    return [
        # ---- A. YC-STYLE PITCH DECK (12 SECTIONS) ----
        {
            "slug": "yc-problem",
            "category": "pitch",
            "section_code": "YC-01",
            "title": "Problem",
            "subtitle": "Fragmented paper folders, mixed lab units, and 3-minute outpatient visits in Bangladesh",
            "content_markdown": (
                "Chronic care in Bangladesh runs on plastic folders. Patients like **Abbu (62, Diabetes + Hypertension + early CKD)** carry handwritten prescriptions from multiple specialist chambers alongside diagnostic printouts from Popular, Ibn Sina, and Labaid—mixing `mmol/L`, `mg/dL`, and `umol/L` on different scales.\n\n"
                "- **Doctors get ~3 minutes** per outpatient visit and cannot reconcile 6 months of scattered papers.\n"
                "- **Cross-chamber polypharmacy goes unnoticed** (e.g., *Seclo 20mg* from a cardiologist + *Sergel 20mg* from a gastroenterologist—two brands of the same PPI class).\n"
                "- **Elderly parents & NRB caregivers** speak Bangla/Banglish, while clinical systems expect English."
            ),
        },
        {
            "slug": "yc-solution",
            "category": "pitch",
            "section_code": "YC-02",
            "title": "Solution",
            "subtitle": "Bilingual voice memory in Bangla/Banglish → verified 1-page English Doctor Brief + QR",
            "content_markdown": (
                "**MediTrackAI** is a neuro-symbolic longitudinal clinical companion for Bangladeshi families.\n\n"
                "1. **Speak or Upload:** Patients talk in Bangla/Banglish (`/ws/live`) and snap photos of handwritten prescriptions or diagnostic PDFs.\n"
                "2. **Verify Deterministically:** Zero-LLM-math engines normalize `mmol/L` ↔ `mg/dL`, compute **CKD-EPI 2021 eGFR**, verify BD brand names against our formulary, and fire **Bangladesh 999** red-flag alerts.\n"
                "3. **Brief the Doctor:** Synthesizes months of scattered records into a **1-page English Doctor Brief PDF** behind a **72-hour expiring QR code**."
            ),
        },
        {
            "slug": "yc-why-now",
            "category": "pitch",
            "section_code": "YC-03",
            "title": "Why Now",
            "subtitle": "Multimodal VLMs + Bangla speech + Sovereign local GPUs + BD PDPA 2026",
            "content_markdown": (
                "- **Multimodal VLMs** can finally parse messy South Asian handwritten prescriptions and `1+0+1` dosing schedules.\n"
                "- **Hybrid Small-Model Serving** (`faster-whisper`, `BGE-M3`, `Qwen3-Reranker`, `MedGemma 4B`) now runs inside an **8 GB GPU**, slashing USD API burn by **60–75%**.\n"
                "- **Bangladesh PDPA 2026** classifies medical & biometric voice data as Sensitive Personal Data—creating an urgent moat for privacy-first, local-scrubbing architectures."
            ),
        },
        {
            "slug": "yc-product-demo",
            "category": "pitch",
            "section_code": "YC-04",
            "title": "Product Demo",
            "subtitle": "3-pillar mobile-first PWA + live Judge Telemetry Drawer",
            "content_markdown": (
                "Try the live seeded **Dhaka Family Demo** (`demo@meditrack.bd` / `MediTrack2026!` or 1-Click Demo Login):\n\n"
                "- **Family Vault:** Switch cleanly between `Self (Sadia)`, `Abbu (Abdul Karim)`, and `Ammu (Rehana Begum)` with strict `patient_profile_id` isolation.\n"
                "- **Records & Trends:** Watch Ibn Sina's `140.5 mg/dL` fasting glucose snap onto Popular/Labaid's `mmol/L` curve (`6.4 -> 7.8 -> 9.1 mmol/L`) and inspect the **Duplicate PPI Alert (`Seclo` + `Sergel`)**.\n"
                "- **Check-In & Visit Prep:** Ask a Banglish question via `/ws/live`, inspect exact `[Rx #id]`/`[Lab #id]` citations in the **Telemetry Drawer**, and scan the **1-Page Doctor Brief QR**."
            ),
        },
        {
            "slug": "yc-market-opportunity",
            "category": "pitch",
            "section_code": "YC-05",
            "title": "Market Opportunity",
            "subtitle": "Urban chronic-care households in Bangladesh + global NRB diaspora + diagnostic labs",
            "content_markdown": (
                "- **Domestic Wedge:** Tens of millions of urban chronic-care patients (Diabetes, Hypertension, Cardiac, Renal, Thyroid) & Dengue seasonal households across Dhaka, Chattogram, and divisional cities.\n"
                "- **High-WTP NRB Anchor:** Millions of Non-Resident Bangladeshis across the UK, US, Canada, Europe, and the Middle East already paying out-of-pocket for aging parents' care back home.\n"
                "- **B2B2C Channel:** Thousands of mid-tier diagnostic centers printing millions of CBC/HbA1c/Lipid reports annually."
            ),
        },
        {
            "slug": "yc-business-model",
            "category": "pitch",
            "section_code": "YC-06",
            "title": "Business Model",
            "subtitle": "Split AI unit economics powering B2C Family Care, NRB Diaspora, and B2B2C Diagnostic QR",
            "content_markdown": (
                "Our **3-Tier Split AI Router** cuts variable compute from `USD 0.61–1.10/MAU/mo` (`BDT 73–132`) in pure cloud down to **`USD 0.26–0.43/MAU/mo` (`BDT 31–52`)**—protecting ~80%+ gross margin and shielding against Bangladesh Bank USD FX caps.\n\n"
                "| Tier | Target Persona | Price | Payment Rails |\n"
                "| :--- | :--- | :---: | :--- |\n"
                "| **Free** | Single Patient | **BDT 0** | 1 Profile, 5 uploads/mo |\n"
                "| **Family Care** | Urban Caregiver | **BDT 299 / mo** | bKash, Nagad, SSLCommerz |\n"
                "| **Diaspora Care** | NRB Caregivers | **USD 4.99 / mo** | Stripe (USD/CAD/GBP/EUR) |\n"
                "| **Smart Lab QR (B2B2C)** | Diagnostic Centers | **BDT 10–15 / report** | Direct B2B + Negative-CAC Funnel |"
            ),
        },
        {
            "slug": "yc-traction",
            "category": "pitch",
            "section_code": "YC-07",
            "title": "Traction",
            "subtitle": "Working Phase 1 production-grade core, verified test suite, and live telemetry",
            "content_markdown": (
                "- **Phase 1 Core Shipped:** 15-table PostgreSQL 16 + `pgvector` schema, 41 FastAPI routes, dual-mode `cloud | hybrid_gpu` AI router, and 4-tab React PWA.\n"
                "- **Curated BD Ontologies Seeded:** 100 BD drug brands, 25 DDI/duplicate rules, 20 LOINC lab definitions, and full Dhaka Family Demo timeline.\n"
                "- **Verified Engineering:** `8/8` automated `pytest` clinical/isolation/RAG/PDF suite passing (`11.98s`), clean TypeScript/Vite production build, and live Uvicorn + Cloudflare Tunnel validation."
            ),
        },
        {
            "slug": "yc-competition",
            "category": "pitch",
            "section_code": "YC-08",
            "title": "Competition",
            "subtitle": "Why generic chatbots, Western EHRs, and local e-pharmacies miss the continuity layer",
            "content_markdown": (
                "| Dimension | Generic LLM Wrappers | Local e-Pharmacies / Telemed | **MediTrackAI** |\n"
                "| :--- | :--- | :--- | :--- |\n"
                "| **Clinical Math & Safety** | LLM guesses eGFR/units | Manual / none | **Deterministic Tier 0 (0% math hallucination)** |\n"
                "| **BD Formulary & DDIs** | Hallucinates *Seclo*/*Sergel* | SKU cart only | **RapidFuzz + `pg_trgm` + cross-Rx duplicate alerts** |\n"
                "| **Cost & USD FX Burn** | `BDT 73–132`/MAU/mo | High call-center/CAC | **Split AI `BDT 31–52`/MAU/mo (60–75% lower USD burn)** |\n"
                "| **Doctor Output** | Walls of chat text | Locked in single app | **Universal 1-Page English PDF + 72h QR** |"
            ),
        },
        {
            "slug": "yc-unique-advantage",
            "category": "pitch",
            "section_code": "YC-09",
            "title": "Unique Advantage",
            "subtitle": "Neuro-symbolic Split AI + cross-chamber longitudinal memory + negative-CAC lab QR moat",
            "content_markdown": (
                "1. **3-Tier Split AI Routing:** Zero-token deterministic Tier 0 (`clinical/*`), sovereign 8 GB GPU Tier 1 (`faster-whisper`, `BGE-M3`, `Qwen3-Reranker`, `MedGemma 4B`), and selective Tier 2 cloud (`gemini-3.1-flash-lite` fast path + `gemini-3.8-flash` cursive VLM).\n"
                "2. **3-Leg Hybrid Clinical RAG:** Banglish glossary expansion + `pgvector` `HALFVEC` HNSW + `tsvector` BM25 + `pg_trgm` drug graph → RRF (`k=60`) + exponential temporal decay.\n"
                "3. **Confidence-Gated HITL:** Medications `<0.85` confidence never auto-commit without 1-tap user confirmation."
            ),
        },
        {
            "slug": "yc-go-to-market",
            "category": "pitch",
            "section_code": "YC-10",
            "title": "Go-To-Market",
            "subtitle": "Months 1–6: Dhaka Clinical Pilot → Paid Consumer/NRB → B2B2C Diagnostic QR",
            "content_markdown": (
                "- **Months 1–2 (Dhaka Pilot):** Onboard 50–100 chronic-care families & 5–10 BMDC physicians reviewing 1-page Doctor Briefs; launch WhatsApp Companion Bot beta.\n"
                "- **Months 3–4 (Paid Consumer & NRB):** Activate bKash/Nagad (`BDT 299/mo`) and Stripe Diaspora (`$4.99/mo`) + managed `L4/A10G` GPU tier.\n"
                "- **Months 5–6 (B2B2C Diagnostic Scale):** Stamp MediTrackAI QR codes onto diagnostic printouts (`BDT 10–15/report`) for 10,000+ monthly reports."
            ),
        },
        {
            "slug": "yc-team",
            "category": "pitch",
            "section_code": "YC-11",
            "title": "Team",
            "subtitle": "Builders uniting AI systems engineering, clinical safety, and Bangladesh healthcare insight",
            "content_markdown": (
                "Our team combines full-stack AI infrastructure, bilingual speech/RAG engineering, and deep local healthcare workflow insight—backed by open-standards collaboration with BMDC clinicians and NRB diaspora contributors."
            ),
        },
        {
            "slug": "yc-vision",
            "category": "pitch",
            "section_code": "YC-12",
            "title": "Vision",
            "subtitle": "Portable, verifiable clinical memory for every family across Bangladesh and South Asia",
            "content_markdown": (
                "MediTrackAI turns scattered paper prescriptions and worried family phone calls into **continuous, verifiable clinical memory**—bridging elderly parents, global NRB caregivers, and busy doctors in three minutes flat, and scaling seamlessly across South Asia and diaspora communities worldwide."
            ),
        },
        # ---- B..O TECHNICAL DOCUMENTATION (14 SECTIONS) ----
        {
            "slug": "tech-overview",
            "category": "technical",
            "section_code": "B",
            "title": "Product Overview",
            "subtitle": "What MediTrackAI does, target personas, and primary clinical workflows",
            "content_markdown": (
                "**MediTrackAI** is a mobile-first clinical memory PWA + FastAPI backend engineered for three core personas:\n"
                "- **Elderly / Chronic-Care Patients:** Voice-first Bangla/Banglish check-ins (`/ws/live`) with noise-resilient VAD and warm Bangla audio responses.\n"
                "- **Dhaka & NRB Family Caregivers:** Multi-profile vault (`Self`, `Abbu`, `Ammu`), automated unit-normalized trend charts, and cross-doctor medication alerts.\n"
                "- **Outpatient Physicians:** Instant, scannable **1-page English Doctor Brief** (`WeasyPrint` PDF + 72-hour expiring public QR view `/brief/:token`)."
            ),
        },
        {
            "slug": "tech-feature-matrix",
            "category": "technical",
            "section_code": "C",
            "title": "Feature Matrix",
            "subtitle": "Live-synced inventory of shipped Phase 1 features and Phase 2 roadmap items",
            "content_markdown": (
                "| Feature Module | Status | Implementation Highlights |\n"
                "| :--- | :---: | :--- |\n"
                "| **Dual-Mode Split AI Router** | `LIVE` | `cloud` (`<50MB` deps) & `hybrid_gpu` (8 GB VRAM) with per-capability fallback |\n"
                "| **3-Leg Hybrid Clinical RAG** | `LIVE` | `pgvector` `HALFVEC` HNSW + `tsvector` BM25 + `pg_trgm` BD Drug expansion + RRF + decay |\n"
                "| **BD Drug Verifier & DDI Engine** | `LIVE` | 100 BD brands, 25 DDI rules, confidence tiers (`>=0.85`), duplicate PPI detection |\n"
                "| **LOINC Normalizer & CKD-EPI 2021** | `LIVE` | `mmol/L` ↔ `mg/dL` ↔ `umol/L`, race-free eGFR, ADA glycemic bands |\n"
                "| **Bangla / Dengue 999 Red-Flag Gate** | `LIVE` | Deterministic symptom & critical lab alerts (`Platelets <50k/100k`, `K+`, `Glucose`, `Hb`) |\n"
                "| **1-Page Doctor Brief PDF + 72h QR** | `LIVE` | Consolidated 1-call `brief_dag.py` + deterministic fallback + `WeasyPrint` + SHA-256 QR |\n"
                "| **Live `/docs` Pitch + CMS + Scheduling** | `LIVE` | Access-controlled YC pitch + technical whitepaper + Mermaid + team + versioning |\n"
                "| **WhatsApp Cloud API + 20k DGDA Sync** | `PLANNED` | Phase 2 Month 1–2 B2C caregiver loop & full national formulary sync |\n"
                "| **bKash/Nagad + Stripe + B2B2C QR** | `PLANNED` | Phase 2 Month 3–6 monetization & diagnostic LIMS webhook |"
            ),
        },
        {
            "slug": "tech-architecture",
            "category": "technical",
            "section_code": "D",
            "title": "Architecture Diagram",
            "subtitle": "Editable Mermaid system topology: UI → API → Split AI Router → PostgreSQL + pgvector",
            "content_markdown": (
                "MediTrackAI separates frontend PWA capture, JWT-authenticated FastAPI orchestration, the 3-Tier Split AI Router, and PostgreSQL 16 + `pgvector` storage. Admins can edit the Mermaid definition live in the Admin CMS panel."
            ),
            "mermaid_diagram": arch_mermaid,
        },
        {
            "slug": "tech-data-flow",
            "category": "technical",
            "section_code": "E",
            "title": "Data Flow Diagram",
            "subtitle": "Input → Pre-Gate → Split AI Processing → Longitudinal Storage → Output → Feedback",
            "content_markdown": (
                "Every voice turn, prescription image, and diagnostic lab report passes through deterministic safety and privacy pre-gates before reaching multimodal or LLM layers, and ends in auditable citations and human confirmation."
            ),
            "mermaid_diagram": dataflow_mermaid,
        },
        {
            "slug": "tech-stack",
            "category": "technical",
            "section_code": "F",
            "title": "Technology Stack",
            "subtitle": "Frontend, Backend, Database, Split AI & Infrastructure layers",
            "content_markdown": (
                "- **Frontend:** React 18, TypeScript, Vite 5, Tailwind CSS, shadcn/ui, Recharts, Mermaid.js, Web Audio PCM16 streamer, React Query.\n"
                "- **Backend:** FastAPI, Uvicorn, SQLAlchemy 2.0, Alembic, `pydantic-settings`, `argon2-cffi`, `PyJWT`, `rapidfuzz`, `weasyprint`, `qrcode`, `sse-starlette`.\n"
                "- **Database:** PostgreSQL 16 (`pgvector/pgvector:pg16` on port `5433`) with `vector 0.8.7` (`HALFVEC` HNSW) and `pg_trgm 1.6` GIN indexes.\n"
                "- **Split AI Stack:** `cloud` (`google-genai`: `gemini-3.1-flash-lite`, `gemini-3.8-flash`, `gemini-embedding-2`, `gemini-2.5-flash-preview-tts`) + `hybrid_gpu` (`faster-whisper` INT8, `BAAI/bge-m3` FP16, `Qwen3-Reranker-0.6B`, Ollama `medgemma-4b-q4`, `silero-vad`).\n"
                "- **Infrastructure:** Docker Compose, Cloudflare Quick Tunnel (`*.trycloudflare.com` via Vite `/api-proxy`), Git hygiene."
            ),
        },
        {
            "slug": "tech-api-docs",
            "category": "technical",
            "section_code": "G",
            "title": "API Documentation",
            "subtitle": "Live-introspected FastAPI route catalog, auth model, and external provider APIs",
            "content_markdown": (
                "All endpoints (except `/health`, `/api/auth/*`, `/api/public/brief/{token}`, and access-controlled `/api/live-docs/public`) require `Authorization: Bearer <JWT>` and optional `X-Profile-Id: <uuid>` for strict family-member isolation. Uploaded files under `/uploads/{path}` require either a Bearer token or an HMAC-SHA256 signed query signature.\n\n"
                "**External APIs Used:** Google Gemini API (`generate_content`, `embed_content`, `tts`) in `cloud`/assist mode; local Ollama HTTP API (`http://localhost:11434`) in `hybrid_gpu` mode.\n\n"
                "See the **Live Route Catalog** in the Live System Telemetry panel below for real-time auto-synced FastAPI routes."
            ),
        },
        {
            "slug": "tech-data-layer",
            "category": "technical",
            "section_code": "H",
            "title": "Data Layer",
            "subtitle": "19 PostgreSQL tables, parsing pipelines, and privacy handling",
            "content_markdown": (
                "- **Clinical & Vault Tables (15 Phase 1 + 4 Live Docs):** `users`, `patient_profiles`, `pdpa_consents`, `checkins`, `prescriptions`, `reports`, `doctor_briefs`, `background_jobs`, `bd_drug_catalog`, `bd_ddi_rules`, `loinc_lab_reference`, `clinical_observations`, `medication_episodes`, `clinical_edges`, `knowledge_chunks`, plus `live_docs_settings`, `live_docs_sections`, `live_docs_team_members`, `live_docs_versions`.\n"
                "- **Dual Vector Columns:** `knowledge_chunks` stores both `embedding_gemini_mm` (`HALFVEC(1536)`) and `embedding_bge_m3` (`HALFVEC(1024)`) indexed via separate HNSW graphs alongside computed `tsvector`.\n"
                "- **Privacy Handling:** Per-profile upload paths, local `MedGemma`/BD regex PHI redaction (`PHONE_BD`, `NID_OR_REG`, `EMAIL`), and versioned bilingual `pdpa_consents`."
            ),
        },
        {
            "slug": "tech-ai-layer",
            "category": "technical",
            "section_code": "I",
            "title": "AI Layer",
            "subtitle": "3-Tier Split AI routing, 3-leg Hybrid RAG, personalization, and TelemetryDrawer explainability",
            "content_markdown": (
                "1. **Tier 0 Deterministic (`$0` tokens):** `unit_normalizer.py`, `risk_calculators.py`, `drug_verifier.py`, `red_flag_gate.py`.\n"
                "2. **Tier 1 Local GPU (`hybrid_gpu`):** `faster-whisper` (`large-v3-turbo`), `BAAI/bge-m3`, `Qwen/Qwen3-Reranker-0.6B`, Ollama `medgemma-4b-q4`.\n"
                "3. **Tier 2 Split Cloud:** `gemini-3.1-flash-lite` (`fast=True`, `20s` timeout + grounded RAG fallback) and `gemini-3.8-flash` (handwritten Rx VLM + 1-call `brief_dag.py`).\n"
                "4. **Explainability:** `TELEMETRY_STORE` captures vector/BM25/trigram/RRF/temporal-decay/rerank scores, citations, PII diffs, and voice tool calls in real time."
            ),
        },
        {
            "slug": "tech-roadmap",
            "category": "technical",
            "section_code": "J",
            "title": "Product Roadmap",
            "subtitle": "Short-term (Phase 1), Mid-term (Months 1–3), Long-term (Months 4–6+)",
            "content_markdown": (
                "- **Short Term (Shipped):** Dual-mode Split AI router, 15-table `pgvector` schema, BD clinical checks, WeasyPrint 1-page QR briefs, `/ws/live` Bangla voice, Live `/docs` CMS.\n"
                "- **Mid Term (Months 1–3):** PostgreSQL RLS + KMS envelope encryption, +880 SSL Wireless OTP, 20,000+ DGDA formulary sync, `evals/` CI gates, WhatsApp Companion Bot beta, Dhaka 50–100 family clinical pilot.\n"
                "- **Long Term (Months 4–6+):** Managed `L4/A10G` vLLM (`MedGemma 27B` + ColPali), Opus `16–24 kbps` audio, `BanSpeech`/`RegSpeech12` regional dialect ASR, bKash/Nagad & Stripe billing, B2B2C Diagnostic QR."
            ),
        },
        {
            "slug": "tech-performance",
            "category": "technical",
            "section_code": "K",
            "title": "Performance & Scalability",
            "subtitle": "Latency budgets, fail-fast resilience, and Phase 2 distributed scaling",
            "content_markdown": (
                "- **Fast-Path Latency Guards:** `20,000ms` single-attempt HTTP clients prevent 45s+ upstream stalls; `/api/rag/search` enforces a `22.0s` `asyncio.wait_for` cap with grounded citation fallback; `brief_dag.py` uses 1 consolidated call + deterministic fallback.\n"
                "- **Async Background SSE:** Heavy VLM OCR & PDF generation run asynchronously via `BackgroundJob` + SSE (`/api/jobs/{id}/events`), upgrading cleanly to **Redis + ARQ** workers in Phase 2.\n"
                "- **Mobile Data Optimization:** Phase 2 switches WebSocket audio from raw PCM16 (`256 kbps`) to **Opus (`16–24 kbps`)**, cutting mobile data usage by **>90%**."
            ),
        },
        {
            "slug": "tech-security",
            "category": "technical",
            "section_code": "L",
            "title": "Security & Privacy",
            "subtitle": "Auth, RBAC, tenant isolation, signed files, and Bangladesh PDPA 2026 compliance",
            "content_markdown": (
                "- **Authentication & RBAC:** `argon2-cffi` password hashing, `PyJWT` Bearer tokens, and role enforcement (`user`, `admin`, `super_admin`) protecting `/api/live-docs/admin/*`.\n"
                "- **Tenant Isolation:** Every clinical query and upload checks `PatientProfile.owner_user_id == current_user.id`.\n"
                "- **File & Share Protection:** `/uploads/` requires valid JWT or HMAC-SHA256 signature; public Doctor Briefs use SHA-256 hashed tokens expiring in 72 hours.\n"
                "- **PDPA 2026 Readiness:** Versioned `pdpa_consents`, local PHI scrubbing, and Phase 2 Postgres RLS + Cloud KMS + Vertex Asia-South Zero-Data-Retention."
            ),
        },
        {
            "slug": "tech-analytics",
            "category": "technical",
            "section_code": "M",
            "title": "Live Analytics & KPIs",
            "subtitle": "Real-time database counts, clinical telemetry, and target evaluation metrics",
            "content_markdown": (
                "The **Live System Telemetry** widget synced directly with PostgreSQL reports live users, family profiles, indexed RAG chunks, BD drug/DDI/LOINC catalog coverage, active inference mode, and recent RAG/PII/voice traces.\n\n"
                "**Phase 2 Production Targets:** Handwritten Rx Generic F1 `>= 95%`, Red-Flag Recall `= 100%`, Unit Normalization `= 100%`, RAG Recall@5 `>= 90%`, Hallucination `< 1%`, p95 Voice TTFA `<= 2.2s`."
            ),
        },
        {
            "slug": "tech-team",
            "category": "technical",
            "section_code": "N",
            "title": "Team & Contributors",
            "subtitle": "Synchronized with the Pitch Deck Team Showcase & NRB collaboration model",
            "content_markdown": (
                "Core builders and contributors are managed centrally via the **Live Team Directory** (linked to `YC-11 Team`). Because `requirements-cloud.txt` installs in `<50 MB` with zero CUDA dependencies and `docker-compose.yml` runs `pgvector` locally, NRB engineers and BMDC clinicians worldwide can collaborate without specialized GPU hardware."
            ),
        },
        {
            "slug": "tech-changelog",
            "category": "technical",
            "section_code": "O",
            "title": "Changelog & Version History",
            "subtitle": "Release milestones and published documentation snapshots",
            "content_markdown": (
                "- **`v1.0.0` (2026-11-20) — Phase 1 Complete + Live `/docs` CMS:** Shipped Dual-Mode Split AI Router (`cloud | hybrid_gpu`), 15-table PostgreSQL + `pgvector` schema, Argon2/JWT Family Vault, 100 BD drugs / 25 DDIs / 20 LOINC labs, Hybrid RAG, WeasyPrint 1-page QR briefs, `/ws/live` Bangla voice, and the access-controlled `/docs` Pitch + Technical Documentation system."
            ),
        },
    ]


def ensure_live_docs_seeded(db: Session) -> Dict[str, Any]:
    settings = db.query(LiveDocsSettings).filter(LiveDocsSettings.id == 1).first()
    created_settings = False
    if not settings:
        settings = LiveDocsSettings(
            id=1,
            visibility_mode="force_on",
            publish_start_at=datetime(2026, 6, 10, 0, 0, 0, tzinfo=BD_TZ),
            publish_end_at=datetime(2026, 6, 14, 23, 59, 59, tzinfo=BD_TZ),
            duration_hours=None,
            team_name="Team MediTrackAI",
            active_version_tag="v1.0.0",
            updated_by="system@meditrack.bd",
        )
        db.add(settings)
        db.flush()
        created_settings = True

    existing_slugs = {s.slug for s in db.query(LiveDocsSection.slug).all()}
    added_sections = 0
    for idx, item in enumerate(_default_sections()):
        if item["slug"] in existing_slugs:
            continue
        md = item["content_markdown"]
        diag = item.get("mermaid_diagram")
        db.add(
            LiveDocsSection(
                slug=item["slug"],
                category=item["category"],
                section_code=item["section_code"],
                title=item["title"],
                subtitle=item.get("subtitle"),
                sort_order=idx,
                is_visible=True,
                content_markdown=md,
                draft_markdown=md,
                mermaid_diagram=diag,
                draft_mermaid=diag,
                has_unpublished_changes=False,
            )
        )
        added_sections += 1

    if db.query(LiveDocsTeamMember).count() == 0:
        default_team = [
            {
                "full_name": "Shayer Mahmud Sowmik",
                "role_title": "Lead Full-Stack & Split-AI Architect",
                "email": "sowmik@meditrack.bd",
                "avatar_url": "",
                "sort_order": 0,
            },
            {
                "full_name": "Sadia Rahman",
                "role_title": "Clinical Product & Caregiver Experience Lead",
                "email": "sadia@meditrack.bd",
                "avatar_url": "",
                "sort_order": 1,
            },
            {
                "full_name": "Dr. Mahmudul Hasan (Advisor)",
                "role_title": "BMDC Clinical Governance & Formulary Reviewer",
                "email": "clinical@meditrack.bd",
                "avatar_url": "",
                "sort_order": 2,
            },
            {
                "full_name": "Tariqul Islam",
                "role_title": "Bangla Speech, Hybrid RAG & Eval Engineer",
                "email": "nlp@meditrack.bd",
                "avatar_url": "",
                "sort_order": 3,
            },
        ]
        for m in default_team:
            db.add(LiveDocsTeamMember(**m, is_active=True))

    db.flush()

    if db.query(LiveDocsVersion).count() == 0:
        all_secs = db.query(LiveDocsSection).order_by(LiveDocsSection.sort_order.asc()).all()
        team = db.query(LiveDocsTeamMember).order_by(LiveDocsTeamMember.sort_order.asc()).all()
        db.add(
            LiveDocsVersion(
                version_tag="v1.0.0",
                summary="Initial Phase 1 YC Pitch Deck & Technical Documentation Release",
                published_by="system@meditrack.bd",
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
                        for s in all_secs
                    ],
                    "team": [
                        {
                            "full_name": t.full_name,
                            "role_title": t.role_title,
                            "email": t.email,
                            "avatar_url": t.avatar_url,
                            "sort_order": t.sort_order,
                            "is_active": t.is_active,
                        }
                        for t in team
                    ],
                },
            )
        )

    db.commit()
    return {"created_settings": created_settings, "added_sections": added_sections}
