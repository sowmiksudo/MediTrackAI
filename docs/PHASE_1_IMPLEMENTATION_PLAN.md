# MediTrackAI — Phase 1 Implementation Plan: Fix All Limitations & Ship the Bangladesh SOTA Core

> **Objective:** Eliminate every verified technical, security, and conceptual limitation in `MediTrackAI`, refocus the product onto a **3-pillar Bangladesh-native chronic-care & caregiver core**, and ship a **dual-mode (`hybrid_gpu | cloud`) SOTA embedding, RAG, voice, and clinical brief engine** engineered for a **1–2 person 48-hour hackathon sprint**.
>
> **Scope Boundary:** Phase 1 covers hackathon-ready implementation, minimal curated BD seed data (`~100` BD brands, `25` DDIs/duplicate-generic rules, `20` LOINC labs), and local/cloud developer parity. Post-hackathon production scale, full PDPA 2026 compliance governance, 20,000+ DGDA sync, WhatsApp bot, Redis/ARQ workers, formal `evals/` benchmark suite, and B2B2C integrations live in [PHASE_2_PLAN.md](./PHASE_2_PLAN.md).

---

## 1. Strategic & Hardware Alignment Summary

| Decision Area | Locked Phase 1 Specification |
| :--- | :--- |
| **Primary Wedge** | Urban middle-class chronic-care patients & family caregivers (e.g., managing `Self`, `Abbu`, `Ammu` diabetes/HTN/cardiac folders). |
| **Core 3 Pillars** | 1. **Bilingual Bangla/Banglish + English Voice Check-In** (with Push-to-Talk & Text fallback)<br>2. **Handwritten BD Prescription & Lab Intelligence** (DGDA brand→generic, duplicate/DDI warnings, LOINC `mmol/L`↔`mg/dL` normalization, Human-in-the-Loop edit modal)<br>3. **Longitudinal 1-Page English Doctor-Ready Brief** (WeasyPrint PDF + expiring read-only QR/WhatsApp share link) & **Deterministic Red-Flag Triage** |
| **Language Bar** | **Input/Voice/OCR:** Bilingual Bangla + Banglish + English (`bn-BD` / `en`).<br>**Clinical UI & Doctor PDF:** English-only (mirrors real Dhaka/Chattogram clinical practice). |
| **Auth & Multi-Tenancy** | Native FastAPI JWT Auth (email/phone + Argon2/bcrypt, OTP-ready interface) + Family Vault (`users` 1:N `patient_profiles`) + mandatory `patient_profile_id` FK + authenticated/signed `/uploads` serving. |
| **AI Orchestration** | Consolidated inside FastAPI as an **async Parallel DAG** (`google-genai` + local Ollama/`MedGemma` router + `asyncio.gather` + native Pydantic Structured Outputs + Postgres-backed `background_jobs` + SSE). Retires standalone port-`5010` Google ADK server and `ai-pipeline/adk-venv`. |
| **Database & Local Infra** | Repo-root `docker-compose.yml` running `pgvector/pgvector:pg16` on default port **`5433`** (configurable via `.env`, avoiding collision with local `5432` containers) + Alembic migrations. Zero Redis in Phase 1. |
| **Dual-Mode AI (`INFERENCE_MODE`)** | **`hybrid_gpu`** (Linux laptop: NVIDIA RTX 5050 Laptop GPU **8 GB VRAM**, Ryzen 5 220 12-thread CPU, 14 GB RAM) runs Silero VAD (CPU) + Bangla `faster-whisper` INT8 + `MedGemma 1.5 4B Q4_K_M` (Ollama) + `BGE-M3` FP16/ONNX + `Qwen3-Reranker-0.6B` INT8 (CPU) under **~6.8 GB / 8.0 GB VRAM**, paired with Cloud Gemini for hard cursive Rx VLM, synthesis, and Bangla TTS.<br>**`cloud`** (Mac teammates: zero CUDA/PyTorch, `<50 MB` `requirements-cloud.txt`) runs `gemini-embedding-2` (1536-dim MRL) + `Gemini 3.8 Flash` + `Gemini 3.5 Flash-Lite` + `Gemini Live API` / Bangla TTS + Flash-Lite/Cohere reranker over identical API contracts. |

---

## 2. Codebase Limitations → Phase 1 Fix Traceability Matrix

| # | Verified Current Limitation (File & Symbol) | Impact / Risk | Exact Phase 1 Fix | Verification Criteria |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Tracked Secrets in Git:** `backend/credentials.json`, `backend/token.json`, `frontend/.env` tracked (`git ls-files`) | Immediate OAuth & API key exposure to judges/auditors | Untrack via `git rm --cached`, rotate OAuth credentials, update `.gitignore` (`.env`, `*.json` tokens, `credentials.json`), provide `.env.example` templates | `git ls-files` shows zero `.env`, `credentials.json`, or `token.json` |
| **2** | **Zero Auth, Multi-Tenancy, or File Protection:** `backend/db/models.py`, `backend/main.py` (`GET /uploads/{file_path:path}` lines 70–128, `allow_origins=["*"]` line 42) | Global unauthenticated PHI exposure; fails PDPA 2026 baseline | Add `users`, `patient_profiles`, `pdpa_consents`; JWT auth; scope every query by `patient_profile_id` ownership; require JWT or HMAC signed token on `/uploads/...`; restrict CORS to `FRONTEND_ORIGINS` | Unauthenticated `/uploads/...` & cross-user profile queries return `401`/`403` |
| **3** | **Fake Keyword RAG:** `backend/utils/medical_rag.py` (`search_medical_data` lines 90–232) | Substring `if/any` matching over 1 `OverallReport` JSON row; zero embeddings; fails on Bangla/synonyms | Build Hybrid RAG in Postgres (`pgvector` `halfvec` HNSW + `tsvector` BM25 + `pg_trgm` fuzzy brand + RRF + exponential temporal decay + reranker + cited chunks `[Rx #id]`) | Banglish query `"amar sugar ar gas er oshudh ki"` retrieves English `HbA1c` & `Sergel/Esomeprazole` chunks with citations |
| **4** | **Broken Voice Tool Loop & Dead Endpoints:** `frontend/src/pages/CheckIn.tsx` (`/medical-search` line 167, `/user-history-search` line 188), `frontend/src/utils/gemini-live-api.js` (`sendToolResult` lines 175–185), `backend/routers/live_ws.py` (lines 294–307) | Tool calls hit 404 endpoints; tool outputs are logged and dropped instead of returned to the model | Execute RAG & DGDA lookup tools **100% server-side inside `/ws/live`**, pass real `functionResponse` turns back to LLM, remove dead browser `fetch()` tool calls | Live voice check-in invokes server-side `search_patient_history` & `lookup_bd_drug` and speaks grounded answer |
| **5** | **No Bangla Voice + Broken VAD:** `backend/routers/live_ws.py` (`SPEECH_RMS_THRESHOLD = 500.0` line 43, `faster-whisper "base"` lines 75–78, `Kokoro lang="en-us"` line 209), `backend/utils/transcribe.py` (`--language en` line 68), `CheckIn.tsx` (`"English or Hindi"` line 55) | Kokoro crashes/mangles Bangla; RMS=500 triggers on fan/room noise; Hindi prompt leakage | Replace RMS VAD with **Silero VAD v5**; swap to **Bangla-tuned `faster-whisper`** (`hybrid_gpu`) / Gemini audio-in (`cloud`) + **Bangla TTS** (Gemini TTS / Chirp 3); remove `"Hindi"` wording; add **Push-to-Talk & Text fallback** | Banglish clip transcribes cleanly in noisy room; audio reply plays natural Bangla/English without false barge-ins |
| **6** | **Fake Hospital Calling & Missing Calendar Module:** `frontend/src/pages/AgentCall.tsx` (omits `tools` from `customSetupConfig` lines 263–280), `backend/utils/gmail_integration.py`, `backend/routers/appointments.py` (`utils.calendar_integration` line 189), `frontend/src/pages/Appointments.tsx` (hardcoded 3 hospitals) | Broken import on calendar route; single global Gmail OAuth; simulated mic call unrealistic for BD hospitals | **Delete** `AgentCall.tsx`, `gmail_integration.py`, and broken calendar endpoint; replace `Appointments.tsx` with **`VisitPrep.tsx`** (1-page QR/WhatsApp Doctor Brief + BD hospital hotline quick-dial) | Zero dead routes/imports; Doctor Brief QR opens read-only brief cleanly |
| **7** | **Hardcoded Retail Insurance Module:** `frontend/src/pages/Insurance.tsx` (hardcoded 3 plans in React & prompt, ignores `/api/insurances`) | <1% BD retail insurance penetration; static prompt demo trap; IDRA risk | **Remove** `Insurance.tsx` & insurance upload route from Phase 1 navigation/UI (repositioned to Phase 2 B2B2C corporate/micro-health) | Sidebar/Bottom Nav shows sharp 3-pillar workflow only |
| **8** | **Unvalidated Clinical Claims & Hallucinated Math:** `ai-pipeline/report_agent/subagents/DiseaseInference/prompt.py` (`confidence: 85`), `RiskScoringandSeverity/prompt.py` (`risk_score: 78`, `overall_health_index`), `LabRiskScorer/prompt.py` | LLM fabricates diagnostic `%` and suggests medication adjustments without clinical formulas | Strip diagnostic `%`, medication-change prompts, and arbitrary 0–100 index; replace with **deterministic `clinical/` calculators** (CKD-EPI eGFR, ADA glycemic band) + **"Observations & Questions for Your Doctor"** + **Red-Flag Gate (incl. Dengue platelets)** | Lab with Creatinine+Age+Sex computes deterministic eGFR; missing inputs output `"Insufficient data"` |
| **9** | **No BD Drug Grounding or `mmol/L` Normalization:** `prescription_agent/prompt.py`, `lab_report_agent/subagents/LabParser/prompt.py` | Handwritten BD brand names hallucinated; `mmol/L` vs `mg/dL` lab comparisons broken | Seed **~100 BD brands** + **25 DDIs/duplicate-generic rules** + **20 LOINC labs**; add `pg_trgm` verifier + **Human-in-the-Loop confirmation modal** for `<0.80` confidence drugs | Uploading Rx with `Seclo 20` + `Sergel 20` flags **Duplicate Generic: Omeprazole + Esomeprazole (PPI)** |
| **10** | **Sync 600s Waterfall, Separate ADK Server & Model Drift:** `ai-pipeline/` (`gemini-3.5-flash`), `live_ws.py` (`gemini-3.8-flash`), `gemini-live-api.js` (`gemini-2.0-flash-exp`), `overall_report.py` (`timeout=600` full-table dump) | Requires 2 venvs + 3 servers; 60–90s blocking timeout; stale model strings | Retire port-`5010` ADK server; consolidate into FastAPI **async Parallel DAG** + `background_jobs` + SSE; centralize models in `ai_core/config.py` (`gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-embedding-2`) | Single backend process; brief job returns `job_id` immediately and completes Parallel DAG in `<15s` |
| **11** | **Unlisted PDF Lib & UI/Schema Bugs:** `backend/utils/pdf_generator.py` (`reportlab` missing from requirements), `Summaries.tsx` (`parseInt("Positive")` -> `NaN`), `Sidebar.tsx` (`w-64` desktop-only), unused `recharts` | Fresh install crashes on PDF generation; all check-in scores render red; broken mobile UX; static matplotlib charts | Replace ReportLab with **WeasyPrint** 1-page English Clinical Brief; standardize `overall_score` enum (`positive\|neutral\|negative`); convert layout to mobile-first bottom nav + desktop rail; render interactive **Recharts** lab trend graphs | Fresh venv builds PDF cleanly; mobile viewport (`375px`) has zero horizontal overflow |

---

## 3. Workstream 1 — Security Hygiene, Cleanup & Repo Restructuring

### 1.1 Secret Remediation & Git Hygiene (First Task — Hour 0)
1. **Untrack leaked files immediately:**
   ```bash
   git rm --cached backend/credentials.json backend/token.json frontend/.env
   ```
   *(And purge from git history / rotate Google OAuth Desktop client secret & revoke refresh token in Google Cloud Console before public repo submission.)*
2. **Update root `.gitignore`:** Add `.env`, `.env.*`, `!.env.example`, `backend/credentials.json`, `backend/token.json`, `backend/uploads/`, `backend/models/`, `*.onnx`, `*.gguf`, `adk-venv/`, `venv/`.
3. **Create clean environment templates:**
   - `backend/.env.example`: `INFERENCE_MODE=cloud` (or `hybrid_gpu`), `DATABASE_URL=postgresql+psycopg://meditrack:meditrack@localhost:5433/meditrack`, `JWT_SECRET`, `FILE_SIGNING_SECRET`, `FRONTEND_ORIGINS=http://localhost:5173`, `GEMINI_API_KEY`, `GEMINI_VLM_MODEL=gemini-3.8-flash`, `GEMINI_FAST_MODEL=gemini-3.5-flash-lite`, `GEMINI_EMBED_MODEL=gemini-embedding-2`, `GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts`, `OLLAMA_BASE_URL=http://localhost:11434`, `LOCAL_MEDGEMMA_MODEL=medgemma-4b-q4`, `LOCAL_WHISPER_MODEL=large-v3-turbo`, `LOCAL_EMBED_MODEL=BAAI/bge-m3`, `LOCAL_RERANKER_MODEL=Qwen/Qwen3-Reranker-0.6B`.
   - `frontend/.env.example`: `VITE_BACKEND_URL=http://localhost:8000` (remove `VITE_GEMINI_API_KEY` completely—no AI API keys in browser bundle!).

### 1.2 Explicit Removals & Archiving
- **Delete / Archive from active runtime:**
  - `frontend/src/pages/AgentCall.tsx` (simulated hospital calling)
  - `frontend/src/pages/Insurance.tsx` (hardcoded retail insurance)
  - `backend/utils/gmail_integration.py`, `backend/utils/google_auth_setup.py`, `backend/setup_google_auth.sh` (global OAuth emailer)
  - `backend/routers/insurances.py`, `backend/routers/hospitals.py`, and calendar/email endpoints in `backend/routers/appointments.py`
  - `backend/models/kokoro/` binaries (`kokoro-v1.0.onnx`, `voices-v1.0.bin`)
  - `backend/uploads/lab_reports/CBC-test-report-format-example-sample-template-Drlogy-lab-report.pdf` (Indian template artifact)
  - Legacy standalone `ai-pipeline/` runtime (`adk api_server` on port `5010` and `ai-pipeline/adk-venv` dependency; migrate any reusable Pydantic shapes into `backend/schemas/`).

### 1.3 Split Dependencies for RTX 5050 vs. Mac Teammates
Replace bloated `backend/requirements.txt` (`134` packages mixing CUDA `torch==2.8.0` + `whisperx` + `pyannote`) with three clean files:
1. **`backend/requirements-base.txt` (<50 MB, installs on macOS/Linux/Docker in <30s):**
   `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `alembic`, `psycopg[binary]`, `pgvector`, `pydantic>=2.10`, `pydantic-settings`, `python-dotenv`, `python-multipart`, `passlib[argon2]`, `pyjwt`, `google-genai>=1.40`, `httpx`, `pillow`, `weasyprint`, `qrcode[pil]`, `numpy`, `websockets`, `rapidfuzz`, `sse-starlette`.
2. **`backend/requirements-cloud.txt` (Mac teammates):** `-r requirements-base.txt` *(runs 100% of app in `INFERENCE_MODE=cloud` with zero CUDA/PyTorch)*.
3. **`backend/requirements-gpu.txt` (RTX 5050 Linux host):** `-r requirements-base.txt` + `faster-whisper>=1.2`, `onnxruntime-gpu`, `FlagEmbedding` (or `sentence-transformers` + `transformers` for `BGE-M3`), `optimum[onnxruntime]`, `silero-vad`, `torch` (CUDA wheel). *(Ollama runs `MedGemma 1.5 4B Q4_K_M` as a local daemon over HTTP `localhost:11434`, isolating GGUF/llama.cpp from Python venv conflicts.)*

---

## 4. Workstream 2 — Docker Compose (`pgvector`), Alembic Migrations, Auth & Family Vault

### 2.1 Root `docker-compose.yml` (Port `5433` Collision-Safe)
Create `/docker-compose.yml` so Linux and Mac teammates boot an identical `pgvector` database without colliding with existing port-`5432` containers (`praanlink-postgres`):
- **Service `db`:** `image: pgvector/pgvector:pg16`
- **Ports:** `"${PG_PORT:-5433}:5432"`
- **Environment:** `POSTGRES_USER=meditrack`, `POSTGRES_PASSWORD=meditrack`, `POSTGRES_DB=meditrack`
- **Init SQL (`backend/db/init_extensions.sql`):** `CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;`
- **Healthcheck:** `pg_isready -U meditrack -d meditrack` + named volume `meditrack_pgdata`.

### 2.2 Complete Unified PostgreSQL Schema (Alembic Migration `0001_phase1_core`)
Migrate `backend/db/models.py` off implicit `Base.metadata.create_all` onto **Alembic**:

1. **Identity, Family Vault & Consent:**
   - `users`: `id (UUID PK)`, `email (unique, nullable)`, `phone_e164 (unique, nullable, +880...)`, `password_hash`, `full_name`, `created_at`.
   - `patient_profiles`: `id (UUID PK)`, `owner_user_id (FK users.id)`, `display_name` (e.g., `"Self"`, `"Abbu"`, `"Ammu"`), `relationship` (`self|parent|spouse|child`), `date_of_birth`, `sex` (`M|F|Other`), `chronic_conditions (JSONB)`, `allergies (JSONB)`, `emergency_contact_phone`, `created_at`.
   - `pdpa_consents`: `id (UUID PK)`, `user_id (FK)`, `patient_profile_id (FK)`, `consent_version`, `accepted_local_storage (bool)`, `accepted_cloud_ai_processing (bool)`, `accepted_at`.
2. **Scoped Core Clinical Tables (All enforce `patient_profile_id UUID FK NOT NULL INDEX`):**
   - `checkins`: `id`, `patient_profile_id`, `audio_path`, `transcript (JSONB)`, `pii_redacted_transcript (JSONB)`, `summary (TEXT)`, `mood`, `symptoms (JSONB)`, `medications_mentioned (JSONB)`, `sleep_quality`, `energy_level`, `concerns (JSONB)`, `red_flags_detected (JSONB)`, `overall_score` (`ENUM('positive','neutral','negative')`), `language_detected`, `created_at`.
   - `prescriptions`: `id`, `patient_profile_id`, `file_path`, `doc_date`, `doctor_name`, `doctor_bmdc_reg`, `hospital`, `diagnosis`, `raw_ocr_text`, `extracted_json (JSONB)`, `verification_status` (`pending_review|confirmed`), `overall_confidence (Float)`, `ddi_alerts (JSONB)`, `created_at`.
   - `reports` (Labs): `id`, `patient_profile_id`, `file_path`, `lab_name`, `report_date`, `raw_ocr_text`, `extracted_json (JSONB)`, `verification_status`, `critical_alerts (JSONB)`, `created_at`.
   - `doctor_briefs` (replaces `overall_reports`): `id`, `patient_profile_id`, `pdf_file_path`, `share_token_hash`, `share_expires_at`, `brief_payload (JSONB)`, `deterministic_scores (JSONB)`, `citations (JSONB)`, `created_at`.
   - `background_jobs`: `id (UUID PK)`, `patient_profile_id`, `job_type` (`rx_parse|lab_parse|brief_gen|reindex`), `status` (`queued|running|completed|failed`), `progress_pct`, `current_step`, `result_id`, `error_message`, `created_at`, `updated_at`.
3. **Bangladesh Clinical Grounding & Temporal Graph Tables:**
   - `bd_drug_catalog`: `id`, `brand_name`, `generic_name`, `strength`, `dosage_form`, `manufacturer`, `indicative_price_bdt`, `atc_code`, `drug_class` + `GIN (brand_name gin_trgm_ops)` + `GIN (generic_name gin_trgm_ops)`.
   - `bd_ddi_rules`: `id`, `drug_a_generic`, `drug_b_generic`, `rule_type` (`duplicate_class|major_ddi|moderate_ddi`), `severity` (`critical|warning|info`), `clinical_note`.
   - `loinc_lab_reference`: `loinc_code (PK)`, `canonical_name`, `aliases (TEXT[])`, `standard_unit`, `alt_units (JSONB: conversion multipliers)`, `ref_low_male`, `ref_high_male`, `ref_low_female`, `ref_high_female`, `critical_low`, `critical_high`.
   - `clinical_observations`: `id`, `patient_profile_id`, `source_type` (`lab|checkin`), `source_id`, `loinc_code (FK)`, `raw_name`, `raw_value`, `raw_unit`, `canonical_value (Float)`, `canonical_unit`, `flag` (`low|normal|high|critical`), `observed_at (TIMESTAMPTZ)`.
   - `medication_episodes`: `id`, `patient_profile_id`, `prescription_id (FK)`, `raw_brand_name`, `matched_drug_id (FK bd_drug_catalog)`, `generic_name`, `dosage`, `frequency_bd` (e.g., `1+0+1`), `duration_days`, `match_confidence (Float)`, `needs_user_confirm (Bool)`, `status` (`active|completed|stopped`), `started_at`, `ended_at`.
   - `clinical_edges`: `id`, `patient_profile_id`, `src_type`, `src_id`, `edge_type` (`PRESCRIBED_FOR|TRIGGERED_ALERT|FOLLOW_UP_OF|DUPLICATE_OF`), `dst_type`, `dst_id`, `metadata (JSONB)`.
4. **Versioned Hybrid RAG Memory (`knowledge_chunks`):**
   - `id (UUID PK)`, `patient_profile_id (FK, INDEX)`, `source_type` (`checkin|prescription|lab_report|medication|observation`), `source_id`, `chunk_text (TEXT)`, `language`, `event_at (TIMESTAMPTZ)`, `chunk_metadata (JSONB)`
   - `tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED` + `GIN(tsv)`
   - **`embedding_bge_m3 halfvec(1024)`** + `HNSW (embedding_bge_m3 halfvec_cosine_ops)` *(for `hybrid_gpu`)*
   - **`embedding_gemini_mm halfvec(1536)`** + `HNSW (embedding_gemini_mm halfvec_cosine_ops)` *(for `cloud` & multimodal PDF/image embeddings)*
   - `bge_sparse_weights (JSONB)` *(optional lexical sparse boost from BGE-M3)*.

### 2.3 Auth, Multi-Profile Scoping & Locked `/uploads`
- **Endpoints:** `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `GET/POST /api/profiles`, `POST /api/profiles/{id}/consent`.
- **FastAPI Dependency `get_active_profile`:** Reads JWT Bearer token + `X-Profile-Id` header, verifies `PatientProfile.owner_user_id == current_user.id`, and passes `profile_id` into every DB query and RAG filter.
- **File Security:** Lock `GET /uploads/{file_path:path}` behind either valid JWT + profile path ownership (`uploads/{profile_id}/...`) or an HMAC-SHA256 short-lived signed token (`?token=...&exp=...`) so PDF viewers/images load safely without exposing global PHI. Restrict CORS to `os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")`.

---

## 5. Workstream 3 — Dual-Mode AI Core (`backend/ai_core/`) & Hybrid RAG Engine

### 3.1 Clean Module Architecture (Replacing `ai-pipeline/`)
```text
backend/ai_core/
├── config.py               # Central Pydantic Settings (INFERENCE_MODE, model IDs, thresholds)
├── router.py               # Factory returning LocalGPUProvider or CloudGeminiProvider
├── schemas.py              # Consolidated Pydantic contracts (Rx, Lab, CheckIn, Brief, Telemetry)
├── providers/
│   ├── base.py             # Abstract interface: embed_text, embed_media, rerank, redact_pii, extract_vlm, synthesize
│   ├── local_gpu.py        # BGE-M3 + CPU Qwen3-Reranker + Ollama MedGemma 1.5 4B + Cloud VLM/TTS assist
│   └── cloud_gemini.py     # Pure Cloud: gemini-embedding-2 + Gemini 3.8 Flash / 3.5 Flash-Lite + Bangla TTS
├── rag/
│   ├── indexer.py          # Chunking + dual/active vector population + clinical_edges builder
│   ├── retriever.py        # pgvector HNSW + tsvector BM25 + pg_trgm + RRF + exp(-λ*age) + Reranker
│   └── reindex.py          # CLI: `python -m ai_core.reindex --target=bge_m3|gemini`
└── pipelines/
    ├── rx_pipeline.py      # Multimodal VLM -> DGDA pg_trgm verify -> DDI/Duplicate check -> HITL status
    ├── lab_pipeline.py     # Multimodal VLM -> LOINC + mmol/L normalizer -> Deterministic Risk & Red-Flag Gate
    └── brief_dag.py        # Parallel asyncio.gather DAG -> Citations -> Deterministic Math -> WeasyPrint PDF
```

### 3.2 Exact RTX 5050 8 GB VRAM Budget (`INFERENCE_MODE=hybrid_gpu`)

| Component | Model & Runtime | Device | Steady-State VRAM | Purpose |
| :--- | :--- | :---: | :---: | :--- |
| **Silero VAD v5** | ONNX | CPU | ~0.01 GB | Noise-immune speech segmentation (replaces `RMS=500`) |
| **Bangla ASR** | Bangla-tuned `faster-whisper` (`large-v3-turbo` INT8 or `bangla-whisper-medium` CT2) | RTX 5050 CUDA | **~1.6 GB** | Bangla + Banglish speech transcription w/ medical hotword prompt |
| **Local Clinical LLM** | `MedGemma 1.5 4B` (`Q4_K_M` GGUF via Ollama) | RTX 5050 CUDA | **~2.9 GB** | (1) **Local PHI/PII scrubber** before Cloud LLM calls (PDPA win!), (2) Instant **local red-flag triage**, (3) Local lab/check-in JSON structuring |
| **Multilingual Embedder** | `BAAI/bge-m3` (FP16 / ONNX CUDA) | RTX 5050 CUDA | **~1.1 GB** | Bangla↔English 1024-dim dense + sparse hybrid vectors |
| **Cross-Encoder Reranker** | `Qwen/Qwen3-Reranker-0.6B` (INT8 ONNX) | Ryzen 5 12-thread CPU | **0.0 GB VRAM** (~0.7 GB RAM) | High-precision reranking of top-20 fused candidates in `<140ms` |
| **CUDA + KV Buffer** | Runtime overhead | RTX 5050 CUDA | **~1.2 GB** | Live-demo OOM safety margin |
| **Total Steady State** | — | **8.0 GB Max** | **~6.8 GB / 8.0 GB** | **1.2 GB safety buffer** *(Ollama `keep_alive` + ASR `compute_type="int8"` enforced)* |

**Cloud-Only Parity (`INFERENCE_MODE=cloud` for Mac Teammates):**
- Embeddings: `gemini-embedding-2` (truncated via MRL to `1536` dims, `halfvec(1536)`). Can embed both text chunks **and raw prescription/lab images/PDFs** in the same vector space!
- Reranking: `Gemini 3.5 Flash-Lite` pointwise/listwise batch reranker (or Cohere Rerank API if `COHERE_API_KEY` set).
- PII Scrubber (Mac mode): Regex + `Gemini 3.5 Flash-Lite` lightweight NER pre-masking (gracefully noted in Telemetry Drawer as `"Cloud Fast-Mask"` vs `"Local MedGemma 4B Hardware Scrubber"`).
- Hard Cursive Rx VLM & Brief Synthesis: `Gemini 3.8 Flash` (used in **both** modes for maximum BD handwriting accuracy!).

### 3.3 Hybrid Retrieval Algorithm (`rag/retriever.py`)
1. **Query Rewrite & Cross-Lingual Expansion:** Expand Banglish symptom/drug terms (e.g., `"gas er oshudh"` → `"gas acidity PPI omeprazole esomeprazole seclo sergel"`) via lightweight bilingual glossary + `Gemini 3.5 Flash-Lite`.
2. **Three Concurrent Postgres Legs (`asyncio.gather`):**
   - **Vector ANN (`pgvector` HNSW):** Top-25 chunks for `patient_profile_id` matching active model column (`embedding_bge_m3` or `embedding_gemini_mm`).
   - **Lexical BM25 (`tsvector`):** Top-25 via `ts_rank_cd(tsv, websearch_to_tsquery('english', expanded_query))`.
   - **Fuzzy Drug/Entity Graph Lookup (`pg_trgm` + `clinical_edges`):** Matches Bangladeshi brand typos (`similarity(brand_name, term) > 0.4`) and fetches linked active `medication_episodes` + latest `clinical_observations`.
3. **Reciprocal Rank Fusion (RRF) + Temporal Decay:**
   $$\text{Score}(d) = \left(\sum_{k \in \{\text{vec, bm25, graph}\}} \frac{w_k}{60 + \text{rank}_k(d)}\right) \times \exp(-\lambda \cdot \text{age\_days}(d))$$
4. **Cross-Encoder Rerank:** Top-20 candidates → `Qwen3-Reranker-0.6B` (CPU) or Cloud Reranker → **Top-6 chunks** returned with immutable provenance tags `[Rx #14 | 2026-10-12]`, `[Lab #8 | 2026-11-01]`, `[CheckIn #22 | 2026-11-18]` plus full score breakdown for the **Judge Telemetry Drawer**.

### 3.4 Parallel DAG Brief Generator (`pipelines/brief_dag.py`)
Replaces the 7-step sequential ADK chain (`timeout=600` in `overall_report.py`) with a Postgres-backed async job (`POST /api/briefs/generate` → returns `202 {job_id}`, frontend subscribes to `GET /api/jobs/{job_id}/events` SSE):
1. **Step 1 (Deterministic Python, <50ms):** Query latest `clinical_observations`, `medication_episodes`, `checkins`, run `unit_normalizer`, `drug_verifier`, `risk_calculators`, and `red_flag_gate`.
2. **Step 2 (Parallel LLM Tasks via `asyncio.gather`, ~4–8s):**
   - Task A: Chronological Event & Bangla Check-In Clinical English Translator
   - Task B: Normalized Lab Trend Narrative (strictly grounded in Step 1 SQL deltas)
   - Task C: Medication Reconciliation & Adherence Questions Summary
3. **Step 3 (Final Synthesis + WeasyPrint PDF + QR Token, ~3s):** Assemble **1-Page English Doctor Brief** (`Gemini 3.8 Flash`, `response_schema=DoctorBriefOutput`, zero diagnostic `%`), generate SHA-256 expiring share token (`72h` TTL), render crisp A4 HTML→PDF via **WeasyPrint** with embedded QR code (`meditrack/brief/<token>`).

---

## 6. Workstream 4 — Minimal BD Clinical Grounding Seed & Deterministic Safety Engine

Create `backend/seeds/` and `backend/clinical/` to move all clinical math, drug verification, and safety triggers out of LLM prompts into auditable Python + PostgreSQL.

### 4.1 Minimal Curated Bangladesh Demo Seed (`backend/seeds/`)
- **`bd_drugs_mvp.json` (~100 curated high-frequency BD chronic/primary-care brands):**
  - *Diabetes (20):* Comet, Glucophage, Diabenol, Secrin, Glumer, Galvus Met, Jardiance, Empagliflozin brands, Mixtard, Lantus, etc.
  - *Hypertension & Cardiac (25):* Bizoran, Camlodin, Amdocal, Osartil, Losartil, Cardobis, Concor, Betaloc, Ecosprin 75, Clopid, Rosuva, Atorva, Lipicon, Furosemide/Lasix.
  - *GI / PPI (15):* Seclo, Losectil, Sergel, Maxpro, Nexum, Panto, Finix, Antacid/Entacyd — explicitly demonstrating **duplicate PPI** detection!
  - *Pain / Fever / Dengue-Risk (12):* Napa, Napa Extra, Ace, Napa Extend, Naproxen/Naprox, Ketorolac, Diclofenac (**NSAID contraindication during suspected Dengue / CKD!**).
  - *Respiratory & Allergy (13):* Monas (Montelukast), Fexo, Alatrol, Azmasol, Sulprex, Doxiva.
  - *Antibiotics & Thyroid (15):* Zimax, Azithro, Cef-3, Cefurox, Moxiflox, Thyrox, Thyronorm.
- **`bd_ddi_rules_mvp.json` (25 core duplicate-class & DDI rules):** e.g., `Omeprazole + Esomeprazole` (duplicate PPI), `Aspirin + Clopidogrel` (bleeding monitor), `NSAID + ARB/ACEi + Diuretic` (AKI triple whammy), `NSAID + suspected Dengue/low platelets` (hemorrhage critical warning), `Metformin + eGFR < 30` (lactic acidosis hold alert), `Dual ACEi + ARB`.
- **`loinc_labs_mvp.json` (20 core LOINC lab definitions):** Fasting Blood Glucose (`1558-6`, canonical `mmol/L`, convert `mg/dL ÷ 18.0182`), Random Glucose, HbA1c (`4548-4`, `%`), Serum Creatinine (`2160-0`, `mg/dL` ↔ `µmol/L ÷ 88.4`), eGFR, Total Cholesterol, LDL, HDL, Triglycerides, Hemoglobin, Platelets (`777-3`, `/µL`), WBC, Hematocrit (Dengue hemoconcentration check), ALT (SGPT), AST, TSH, Serum Potassium (`2823-3`), Sodium, Uric Acid, Urine Albumin.

### 4.2 Deterministic Clinical Modules (`backend/clinical/`)
1. **`unit_normalizer.py`:** Normalizes any lab unit (`mg/dL` ↔ `mmol/L` ↔ `µmol/L`) to canonical units before storing `clinical_observations`. Returns both canonical BD unit (`mmol/L`) and US equivalent in Doctor Brief tooltips.
2. **`drug_verifier.py`:** Matches VLM-extracted medicine names against `bd_drug_catalog` using PostgreSQL `pg_trgm` + `rapidfuzz`. Assigns `confidence >= 0.85` (Auto-matched), `0.60–0.84` (Amber — needs confirmation), `< 0.60` (Red — manual edit required). Runs `bd_ddi_rules` across all active `medication_episodes`.
3. **`risk_calculators.py`:**
   - **CKD-EPI 2021 Creatinine eGFR** (deterministic formula when Creatinine + Age + Sex exist; otherwise returns `status="insufficient_data", missing=["serum_creatinine"]`).
   - **ADA Glycemic Banding** (`Normal <5.7%`, `Prediabetes Range 5.7–6.4%`, `Elevated >=6.5%` HbA1c; Fasting `<5.6`, `5.6–6.9`, `>=7.0 mmol/L`).
   - **Zero Unvalidated Diagnostic `%`:** Remove `confidence` % and arbitrary `0–100` `overall_health_index` from all schemas and prompts; rename UI section to **"Clinical Observations & Questions for Your Doctor"**.
4. **`red_flag_gate.py`:** Deterministic lab + symptom red-flag detector:
   - *Lab criticals:* Platelets `< 100,000 /µL` (Dengue warning) or `< 50,000 /µL` (Critical!), K+ `> 6.0` or `< 2.8 mmol/L`, Glucose `< 3.9` or `> 16.7 mmol/L`, Hgb `< 7.0 g/dL`, eGFR `< 30`.
   - *Symptom criticals (Bangla/Banglish + English keywords + local `MedGemma 4B` classifier):* crushing chest pain (`বুকে ব্যথা`), breathing difficulty (`শ্বাসকষ্ট`), slurred speech/weakness on one side, black/bloody stool, persistent vomiting with fever. Immediately surfaces **Emergency Alert Banner + BD `999` / Nearest ER**.

---

## 7. Workstream 5 — Bilingual Bangla/Banglish Voice Pipeline (`/ws/live`) Fix

1. **Audio Segmentation (Stage-Noise Proof):** Replace `SPEECH_RMS_THRESHOLD = 500.0` in `backend/routers/live_ws.py` with **Silero VAD v5** operating on 512-sample frames (`32ms` at `16kHz`) with speech probability threshold `0.60`, minimum utterance `350ms`, and deliberate barge-in threshold (`350ms` sustained speech) so ceiling fans or hackathon hall chatter never trigger false cutoffs.
2. **Dual-Mode ASR / LLM / TTS Flow inside `/ws/live`:**
   - **`hybrid_gpu` mode:** User PCM16 → **Silero VAD** → **Local Bangla-tuned `faster-whisper` (CUDA INT8)** → **Local `MedGemma 4B` PII Scrubber + Red-Flag Gate** (parallel) → **`Gemini 3.8 Flash`** (with server-side tools: `search_patient_history`, `lookup_bd_drug`, `get_normalized_labs`) → stream sentence chunks to **Bangla-capable Cloud TTS** (`Gemini 2.5 Flash TTS` or Google Cloud `Chirp 3` `bn-IN`/`bn-BD` voice, falling back gracefully to Web Speech / text if TTS quota hits) → stream 24kHz PCM16 + live transcript/citations over WebSocket.
   - **`cloud` mode:** User PCM16 → **Silero VAD** → **`Gemini 3.8 Flash` native multimodal audio-in** (or **Gemini Live API** `gemini-live` bidirectional stream) with identical **server-side tool execution** + **Bangla TTS** output.
3. **Fix Tool-Calling Loop:** Remove browser-side tool HTTP calls (`CheckIn.tsx` lines 160–206) and stubbed `sendToolResult()` (`gemini-live-api.js` line 175). Execute tools inside `live_ws.py`, push `{type: "tool_event", tool, citations, latency_ms}` JSON frames to the frontend for live UI badges + Judge Telemetry Drawer, and append `types.Part.from_function_response(...)` back into `history` so the model speaks the retrieved answer.
4. **Push-to-Talk & Text Fallback + Fix `overall_score`:**
   - Add a **Hold-to-Talk** toggle and **Bangla/Banglish Text Input** bar inside `CheckIn.tsx` sharing the exact same WebSocket/REST session (critical insurance against loud hackathon demo rooms!).
   - Standardize check-in summarizer output `overall_score` to strict enum `Literal["positive", "neutral", "negative"]` matching UI badges (fixes `parseInt("Positive") -> NaN` in `Summaries.tsx`).

---

## 8. Workstream 6 — 3-Pillar Mobile-First Frontend, 1-Page Doctor Brief & Judge Telemetry

1. **Responsive App Shell (`Layout.tsx` + `Sidebar.tsx`):**
   - Desktop (`lg+`): Collapsible sidebar with **Active Family Profile Switcher** (`Self`, `Abbu`, `Ammu`, `+ Add Profile`) and PDPA Consent badge.
   - Mobile (`<768px`): Fixed bottom navigation bar across **4 clean tabs**: `Check-In`, `Upload`, `Records` (Summaries & Trends), `Visit Prep` (Doctor Brief & Hotlines). Remove `Appointments.tsx` (replaced by `VisitPrep.tsx`), `AgentCall.tsx`, and `Insurance.tsx`.
2. **Pillar 1 — `CheckIn.tsx`:**
   - Bilingual English/Bangla-script/Banglish prompt (`"Speak naturally in Bangla, Banglish, or English"` — zero `"Hindi"` references).
   - Live scrolling conversation transcript + **citation pills** (`[Lab: HbA1c 8.1%]`, `[Rx: Comet 500]`) + **Red-Flag Emergency Card** (`Call 999`) + Push-to-Talk / Text input toggle.
3. **Pillar 2 — `Upload.tsx` (Human-in-the-Loop BD Rx & Lab Flow):**
   - Mobile camera capture (`accept="image/*,.pdf"`, `capture="environment"`) + async job progress bar via SSE.
   - **Interactive Verification Modal:** Lists extracted medicines with **DGDA Generic Tag + BDT price**, confidence color pill (Green `>=0.85`, Amber `<0.85`), 1-click dropdown suggestions from `bd_drug_catalog`, and prominent **Duplicate-Generic / DDI Warning Banner** before committing to the database.
4. **Pillar 3 — `Summaries.tsx` & `VisitPrep.tsx` (1-Page English Doctor Brief):**
   - `Summaries.tsx`: Fix score badges, add interactive **Recharts** trend charts over `clinical_observations` (`HbA1c %`, `Glucose mmol/L`, `Creatinine mg/dL`, `Platelets`), active vs. past `medication_episodes`.
   - `VisitPrep.tsx`: Trigger `Prepare 1-Page Doctor Brief` (SSE progress) → embedded preview + **WeasyPrint A4 PDF download** + **Expiring QR Code & WhatsApp Share button** (`https://wa.me/?text=...` linking to public read-only `/brief/:token` view) + curated **Dhaka/BD Hospital Emergency & Appointment Hotlines** (`999`, Square `10616`, Evercare `10678`, United `10666`, Labaid `10606`).
5. **Hackathon Judge Showcase — `AI Telemetry & Grounding Drawer`:**
   - Toggleable drawer accessible from header badge showing:
     - Active Mode badge (`Hybrid RTX 5050` vs `Cloud API`) + live GPU VRAM indicator (`nvidia-smi` API endpoint in `hybrid_gpu` mode)
     - **PDPA Local Privacy Proof:** Side-by-side diff of Raw Bangla Transcript vs. `MedGemma 4B` PII-Redacted Cloud Payload (`[PATIENT_NAME]`, `[PHONE_REDACTED]`)
     - **RAG Retrieval Breakdown:** Top chunks with `BGE-M3` dense, `tsvector` BM25, `pg_trgm`, temporal decay, and `Qwen3-Reranker` scores + per-step latency (`ms`).

---

## 9. 48-Hour Execution Schedule & Team Split

### 2-Person Parallel Split (Linux RTX 5050 + Mac Teammate)
- **Person A (Linux RTX 5050 — AI Core, GPU & Voice):** Local `docker-compose.yml` (`pgvector:5433`), `backend/ai_core/` router, Ollama `MedGemma 1.5 4B Q4_K_M`, `BGE-M3` + `Qwen3-Reranker`, Silero VAD + Bangla `faster-whisper` + server-side `/ws/live` tool loop, WeasyPrint brief PDF, Telemetry endpoint.
- **Person B (Mac `INFERENCE_MODE=cloud` — Auth, Schema, Seed, Frontend):** Alembic migrations + JWT Auth + Family Profiles, `requirements-cloud.txt`, curated `bd_drugs_mvp` / `bd_ddi_rules_mvp` / `loinc_labs_mvp` JSON seeds, `clinical/` deterministic calculators & normalizer, mobile-first React layout + `Upload.tsx` HITL modal + `Summaries.tsx` Recharts + `VisitPrep.tsx` QR Brief + Auth/Profile UI.

### Solo Execution Order (48 Hours)
| Window | Milestone | Key Deliverables |
| :--- | :--- | :--- |
| **Hrs 0–10** | **Foundation, Hygiene & Auth** | Purge tracked secrets; add `docker-compose.yml` (`pgvector:5433`); split requirements; Alembic schema (`users`, `patient_profiles`, `knowledge_chunks`, BD seeds schema); JWT Auth + Profile Switcher + locked `/uploads`. |
| **Hrs 10–22** | **Dual-Mode AI Core, BD Seed & Hybrid RAG** | Seed ~100 BD drugs + 25 DDIs + 20 LOINC labs; build `ai_core/` (`hybrid_gpu` + `cloud`); wire `BGE-M3`/`gemini-embedding-2` + `tsvector` + `pg_trgm` + RRF + `Qwen3-Reranker`; build `clinical/` deterministic modules + `rx_pipeline` / `lab_pipeline`. |
| **Hrs 22–34** | **Bangla Voice & Parallel Brief DAG** | Fix `/ws/live` with Silero VAD, Bangla ASR/TTS, server-side tool loop, Push-to-Talk & text fallback; build async `brief_dag.py` + `background_jobs` SSE + WeasyPrint 1-page English PDF + expiring `/api/briefs/{token}` QR endpoint. |
| **Hrs 34–44** | **3-Pillar Mobile UI & Judge Drawer** | Delete `AgentCall.tsx`/`Insurance.tsx`; ship responsive bottom-nav shell, `Upload.tsx` HITL verification modal, `Summaries.tsx` Recharts trends, `VisitPrep.tsx` QR/WhatsApp Brief, and **AI Telemetry & PII-Redaction Drawer**. |
| **Hrs 44–48** | **Hardening, Demo Seed & Rehearsal** | Seed realistic *"Abbu (Diabetes + HTN + Dengue check)"* multi-visit demo profile; verify VRAM ceiling `<7.2 GB` on RTX 5050 and clean `cloud` boot on Mac; rehearse live Bangla voice + duplicate-PPI Rx demo + offline PTT backup. |

---

## 10. Phase 1 Acceptance & Verification Checklist

1. **Repo & Security Gate:**
   - `git ls-files backend/credentials.json backend/token.json frontend/.env` → empty output.
   - `curl -i http://localhost:8000/uploads/...` without JWT/signed token → `401 Unauthorized`.
   - Cross-user `X-Profile-Id` access → `403 Forbidden`.
2. **Mac `cloud` Mode Zero-CUDA Parity Gate:**
   - Install `pip install -r backend/requirements-cloud.txt` on macOS → succeeds cleanly with zero `torch`/`nvidia` packages; `INFERENCE_MODE=cloud uvicorn main:app` passes health, Rx upload, lab normalization, hybrid RAG, and Doctor Brief PDF generation.
3. **RTX 5050 `hybrid_gpu` VRAM & Latency Gate:**
   - Start Ollama `medgemma-4b-q4` + FastAPI `INFERENCE_MODE=hybrid_gpu`; run concurrent voice check-in + RAG retrieval + red-flag triage while polling `nvidia-smi` → **peak VRAM <= 7.2 GB / 8.0 GB**, zero OOMs.
4. **End-to-End BD Clinical Smoke Tests (`pytest`):**
   - *Rx Duplicate-Generic Test:* Upload sample Rx containing `Seclo 20` and `Sergel 20` → `drug_verifier` returns confidence match + `duplicate_class` alert (`Omeprazole` + `Esomeprazole`).
   - *Lab Unit & Red-Flag Test:* Upload glucose `17.5 mmol/L` & platelets `42,000 /µL` → normalized in `clinical_observations` + triggers critical red-flag alert (`999` / ER).
   - *Cross-Lingual RAG Test:* Query `"abbu er pressure ar sugar er obostha ki"` → returns ranked English chunks with `RRF + Rerank` scores and valid `[Rx #...]` / `[Lab #...]` citations.
   - *1-Page Brief & QR Test:* `POST /api/briefs/generate` completes `<15s` via SSE; PDF renders 1 page via WeasyPrint; QR token URL returns read-only JSON/HTML brief and expires cleanly.
