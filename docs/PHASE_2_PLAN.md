# MediTrackAI — Phase 2 Plan: Bangladesh Production Scale, PDPA Compliance & B2B2C Expansion (Months 1–6)

> **Purpose:** Transform the Phase 1 hackathon-winning 3-pillar core ([PHASE_1_IMPLEMENTATION_PLAN.md](./PHASE_1_IMPLEMENTATION_PLAN.md)) into a **clinically governed, PDPA 2026-compliant, financially sustainable Bangladesh digital health platform** serving urban chronic-care families (B2C & diaspora) and diagnostic/clinic partners (B2B2C).

---

## 1. Strategic Vision & Phase 1 → Phase 2 Graduation Gates

### Dual-Wedge Bangladesh Go-To-Market
1. **Primary Consumer Wedge (Months 1–3):** Urban middle-class chronic-care patients (Diabetes, Hypertension, Cardiac, Renal, Thyroid) and their family caregivers—including adult children in Dhaka/Chattogram and Bangladeshi diaspora abroad managing elderly parents' paper folders.
2. **Primary Monetization & Distribution Moat (Months 3–6):** **B2B2C Diagnostic Centers, Clinics, and Corporate Wellness**—embedding *"Scan QR on your lab report for a Bangla Voice Explanation & Longitudinal Trend Brief"* to solve B2C Customer Acquisition Cost (CAC) and ingest crisp digital lab values before they become blurry photos.

### Hard Exit Gates Required to Enter Phase 2
Phase 2 execution begins only after Phase 1 delivers:
- Zero tracked credentials, JWT auth + `patient_profile_id` isolation, and protected file downloads.
- Operational dual-mode (`hybrid_gpu | cloud`) AI router with `pgvector` Hybrid RAG + deterministic BD clinical checks (`drug_verifier`, `unit_normalizer`, `red_flag_gate`).
- Verified 1-page English Doctor Brief (WeasyPrint PDF + expiring QR token) and working Bangla/Banglish voice check-in.

---

## 2. Workstream 1 — Bangladesh PDPA 2026 Compliance, Security & Clinical Governance

Bangladesh's **Personal Data Protection Act (PDPA), 2026** (evolving from the late-2025 Ordinance) designates physical/physiological health conditions, clinical records, biometric voiceprints, and genetic data as **Sensitive Personal Data**. Failing this standard blocks institutional diagnostic/insurer partnerships and creates legal exposure.

### 1.1 PDPA 2026 Operational Package
- **Bilingual Informed Consent Ledger:** Granular versioned consent (`pdpa_consents`) presented in plain Bangla and English separating: (a) encrypted local record storage, (b) caregiver sharing permissions, and (c) cross-border cloud AI inference.
- **Data Residency & Zero-Data-Retention (ZDR) AI Routing:**
  - Route all cloud LLM/VLM calls exclusively through **Vertex AI Asia-South (`asia-southeast1` Singapore / `asia-south1` Mumbai)** enterprise endpoints configured for **Zero Data Retention** (prompts/images never logged or used for model training).
  - Run mandatory **local PHI/PII de-identification** (`MedGemma 4B` / NER scrubber on sovereign GPU) before external cloud calls whenever operating in sovereign/B2B mode.
- **Data Subject Rights Automation (DSAR):**
  - Self-serve **Full Data Export** (JSON + ZIP of original PDFs/audio) and **Cryptographic Right-to-Erasure** (`DELETE /api/account/erase` cascading through PostgreSQL tables, `knowledge_chunks` vectors, object storage blobs, and KMS key shredding).
- **72-Hour Breach Response SOP:** Automated anomaly alerting on bulk PHI reads + audit export ready for Bangladesh Data Protection Authority reporting.

### 1.2 Production Security Hardening
- **Envelope Encryption (AES-256-GCM):** Encrypt sensitive PHI columns (`ocr_text`, `transcript`, `raw_ocr_text`) and uploaded files using per-tenant Data Encryption Keys wrapped by Cloud KMS.
- **PostgreSQL Row-Level Security (RLS):** Enforce `patient_profile_id` isolation directly inside Postgres RLS policies (`SET LOCAL app.current_user_id = ...`), eliminating bug-based cross-tenant leaks.
- **Immutable PHI Audit Trail:** Append-only `phi_access_audit` table logging every read, download, brief share token access, and caregiver switch (`actor_id`, `ip`, `resource`, `action`, `timestamp`).
- **Bangladesh Phone OTP Auth:** Add **+880 SMS OTP** login/verification via local BD SMS aggregators (**SSL Wireless** / **BulkSMSBD**) alongside passkey/JWT refresh rotation, rate limiting (Redis sliding window), and WAF rules.

### 1.3 Clinical Governance (BMDC & DGHS Alignment)
- **BMDC Physician Advisory Board (3–5 clinicians):** Internal Medicine, Cardiology, and Endocrinology consultants review Doctor Brief layouts, red-flag thresholds, and disclaimer wording.
- **Strict Non-Diagnostic CDS Guardrails:** Maintain hard separation between **Clinical Decision Support / Summarization** (allowed) and **Autonomous Diagnosis or Prescribing** (prohibited). All medication edits require explicit patient/pharmacist/doctor verification.
- **Clinical Incident Logging:** Dedicated *"Report AI Extraction Error"* button on every Rx/Lab card feeding an anonymized clinician review queue.

---

## 3. Workstream 2 — Full Bangladesh Clinical Knowledge Base & Offline Evaluation Suite

### 2.1 Automated 20,000+ DGDA / MedEx Bangladesh Drug Sync
- **Scale Up from 100 MVP Seed → Full National Formulary:** Build an automated ingestion & normalization pipeline (`scripts/sync_dgda_catalog.py`) tracking **20,000+ Bangladesh DGDA-approved brand formulations** (brand name, generic composition, strength, dosage form, manufacturer, pack MRP in BDT, ATC code).
- **Full Drug-Drug Interaction (DDI) & Contraindication Matrix:** Expand from 25 rules to a structured **RxNorm / OpenFDA / BNF-aligned DDI graph** covering renal dosing alerts (linked deterministically to **CKD-EPI eGFR**), pregnancy/lactation cautions, and duplicate-molecule detection across Bangladeshi brand aliases.
- **Generic Cost-Saving Transparency:** Surface verified generic equivalents and indicative MRP ranges inside the patient UI (never auto-substituting; displaying *"Same generic molecule — ask your doctor/pharmacist"*).

### 2.2 Expanded LOINC Ontology & Validated Risk Calculators
- **Full LOINC + BD Diagnostic Panel Mapping:** Cover **300+ common Bangladesh diagnostic tests** (CBC, Dengue NS1/IgM/IgG, Typhoid/Widal caveats, HbA1c, OGTT, Lipid Profile, LFT, RFT/Electrolytes, Thyroid, Ferritin/Vitamin D/B12, Urine R/M/E, ACR) including age/sex/pregnancy reference range stratification.
- **Validated Deterministic Calculators (Zero LLM Guessing):**
  - **WHO South-Asia Region Laboratory & Non-Laboratory CVD 10-Year Risk** (explicitly calibrated for Bangladesh epidemiology).
  - **FINDRISC Type-2 Diabetes Risk Score.**
  - **CKD-EPI 2021 eGFR + KDIGO Albuminuria Staging.**

### 2.3 Formal BD Clinical Evaluation Harness (`evals/`) & CI Regression Gates
Build a permanent automated benchmark suite run before every model or prompt release:

| Eval Dataset | Size | Measured Metrics | Release Gate (Must Pass) |
| :--- | :---: | :--- | :--- |
| **Handwritten BD Rx Benchmark** *(de-identified real Dhaka/Chattogram chamber pads)* | 120 Rx images | Generic Extraction F1, Strength Exact Match, Duplicate-Class Precision | **Generic F1 ≥ 95%** · Strength ≥ 92% |
| **Banglish & Dialect Voice Set** *(BanSpeech / RegSpeech12 + noisy indoor recordings)* | 100 audio clips | Medical Term WER, Intent Accuracy, Red-Flag Recall | **Red-Flag Recall = 100%** · Med Term WER ≤ 12% |
| **Longitudinal Multi-Lab Cases** *(mixed `mmol/L` & `mg/dL`, multi-visit)* | 50 patient timelines | Unit Normalization Accuracy, Retrieval Recall@5, Citation Faithfulness | **Normalization = 100%** · **Recall@5 ≥ 90%** · **Hallucination < 1%** |
| **Voice End-to-End Latency** | 50 turns | p50 / p95 time-to-first-audio (TTFA) | **p95 TTFA ≤ 2.2s** |

---

## 4. Workstream 3 — Production Infrastructure, Async Workers & GPU Serving Scale

### 3.1 Migration from Phase 1 Monolith Tools → Production Distributed Stack

| Layer | Phase 1 (Hackathon) | Phase 2 (Bangladesh Production) | Why & Trigger |
| :--- | :--- | :--- | :--- |
| **Task Queue** | Postgres `background_jobs` + FastAPI background tasks | **Redis + ARQ** (or Celery) dedicated worker pool + dead-letter queue + idempotency keys | Prevents heavy VLM/PDF jobs from starving API latency; survives container restarts |
| **File & PHI Storage** | Local `backend/uploads/` | Encrypted private **Cloudflare R2 / AWS S3 (`ap-southeast-1`) / GCS** + short-lived signed URLs + ClamAV malware scan | Eliminates single-node disk bottleneck and satisfies encrypted off-host backup rules |
| **GPU Inference Serving** | Laptop RTX 5050 (`8 GB`) Ollama + local Python | **Managed Single-GPU Inference Node (`L4` or `A10G` 24 GB VRAM via Modal / RunPod / GKE Autopilot)** running **vLLM / SGLang** | Unlocks **`MedGemma 27B` (4-bit ~15 GB VRAM)** or high-throughput **`MedGemma 1.5 4B`** + `BGE-M3` + `Qwen3-Reranker` at scale |
| **Visual PDF Retrieval** | Text chunk + `gemini-embedding-2` | Add **ColPali / ColQwen late-interaction visual retrieval** (`pgvector` multi-vector / Qdrant hybrid index) for multi-page lab PDFs & radiology scans | Eliminates OCR table-splitting failures on complex multi-column diagnostic printouts |
| **Observability** | Console logs + Judge Drawer | **OpenTelemetry + Langfuse / Arize AX** tracing + per-user BDT/USD token cost ledger + Prometheus/Grafana alerts | Tracks model drift, RAG retrieval hit rates, and unit economics in real time |

### 3.2 Production Unit Economics Target (5,000+ Monthly Active Chronic Users)
- **Hybrid GPU Amortized Cost (`1× L4/A10G` handling ASR, `BGE-M3`, `Qwen3-Reranker`, PII/Triage + `Gemini 3.8 Flash` for cursive Rx VLM/synthesis):** **~USD 0.26 – 0.43 / MAU / mo (BDT 31 – 52)** vs. Pure Cloud **~USD 0.61 – 1.10 / MAU / mo (BDT 73 – 132)**.
- **FX Cap Mitigation:** Offloading ~60–75% of compute onto flat-rate GPU infrastructure shields the company from Bangladesh Bank cross-border USD card/remittance friction and lowers gross margin vulnerability.

---

## 5. Workstream 4 — Bangladesh Distribution Channels (WhatsApp, Caregiver Loop & Mobile PWA)

In Bangladesh, **WhatsApp is the real operating system of healthcare coordination**. Forcing elderly patients to log into a standalone web portal limits retention.

1. **WhatsApp Cloud API Companion Bot (`Meta Business Verified`):**
   - **Zero-Friction Ingestion:** Patient or caregiver forwards a prescription photo, lab PDF, or **Bangla voice note** directly to MediTrackAI's WhatsApp number → automatically triggers `rx_pipeline` / `lab_pipeline` / `checkin` and replies in Bangla/English with extracted medicines, duplicate alerts, and a link to the updated vault.
   - **Proactive Caregiver Loop:** When `Ammu` misses a morning check-in or uploads a lab with elevated HbA1c / dropping Dengue platelets, an instant WhatsApp summary alert goes to her adult child (`Primary Caregiver`) in Dhaka, London, Toronto, or New York.
   - **Medication Refill & Follow-Up Nudges:** WhatsApp reminders aligned to Bangla meal times (`সকাল/দুপুর/রাত` — before/after meals).
2. **Mobile PWA / Capacitor Android App:**
   - Offline-queued document capture (captures high-res camera photo locally on flaky 3G/4G in lifts/hospital basements and uploads reliably when signal returns).
   - Multi-caregiver RBAC (`Owner`, `Co-Caregiver`, `Read-Only Doctor QR`).

---

## 6. Workstream 5 — Bangla Regional Dialects & Speech Pipeline Maturity

Phase 1 relies on general Bangla/Banglish ASR and cloud Bangla TTS, which underperform on regional accents outside central Dhaka. Phase 2 addresses this systematically:
1. **Dialect-Robust ASR Fine-Tuning:** Benchmark and LoRA fine-tune `whisper-large-v3-turbo` / **Spring Lab Bengali-Streaming Zipformer** against **`BanSpeech`**, **`RegSpeech12`**, and **`BRDialect`** datasets covering **Chattogram, Sylhet, Noakhali, Barishal, Rajshahi, and Khulna** accents plus a curated **5,000-term Bangladeshi Medical & Brand Lexicon** (so *"Napa Extra"*, *"Bizoran"*, *"Sergel"*, *"HbA1c"*, *"Creatinine"* never mistranscribe).
2. **Native Bangladeshi (`bn-BD`) TTS Tuning:** Eliminate Indian-Bengali (`bn-IN`) prosody mismatch via `bn-BD` neural voice selection / custom voice tuning (`Chirp 3` / `ElevenLabs` / self-hosted `VITS-Bengali` MOS ~4.49 for offline/low-cost tiers).
3. **Low-Bandwidth Audio Streaming:** Switch browser/app WebSocket audio ingress from raw PCM16 (`256 kbps`) to **Opus (`16–24 kbps`)**, cutting mobile data consumption by **>90%** on Robi/GP/Banglalink 4G networks.

---

## 7. Workstream 6 — Monetization, Local Payments & B2B2C Ecosystem Expansion

### 6.1 Consumer & Diaspora Subscription Tiers
| Tier | Target Persona | Price | Included Features | Payment Rails |
| :--- | :--- | :---: | :--- | :--- |
| **Free** | Trial / Single Patient | **BDT 0** | 1 Profile, 5 Rx/Lab uploads/mo, basic English Doctor Brief | — |
| **Family Care** | Urban Caregiver (Dhaka/Ctg) | **BDT 299 / mo** *(~BDT 2,999/yr)* | Up to **5 Family Profiles**, unlimited OCR + DDI/Duplicate alerts, Bangla Voice Check-Ins, WhatsApp Caregiver Alerts | **bKash, Nagad, SSLCommerz** |
| **Diaspora Care** | NRBs supporting aging parents in BD | **USD 4.99 / mo** | Family Care + Priority English/Bangla Alerts + Automated Monthly Parent Health Digest + Multi-Timezone Sharing | **Stripe (USD/CAD/GBP/EUR)** |

### 6.2 B2B2C Diagnostic Center & Clinic Partnerships (Months 3–6)
- **Product:** *"Smart Lab Companion API & QR Stamp"* — Partner mid-tier diagnostic centers in Dhaka/Chattogram print a MediTrackAI QR code on every CBC/Lipid/HbA1c printout (or push HL7/JSON via LIMS webhook).
- **Patient Experience:** Patient scans QR → hears a **Bangla voice walkthrough** of their results + sees multi-visit trends compared against past reports.
- **Pricing:** **BDT 10–15 per report** (or BDT 25,000–75,000/month SaaS per branch) — turning diagnostic centers into a negative-CAC acquisition funnel for Family Care upgrades.

### 6.3 Phase 2B Ecosystem Integrations (Only After Core Clinical PMF)
- **1-Click Pharmacy Refill Handoff:** Deep-link verified active prescriptions to licensed BD e-pharmacies (**Arogga**, **MedEasy**) via referral/affiliate API.
- **Telemedicine Warm Handoff:** Attach the 1-page Doctor Brief JSON/PDF directly when booking a video consult with **DocTime / Praava / Partner Clinics**.
- **IDRA-Compliant Corporate & Micro-Health Insurance Guidance:** Re-introduce insurance *only* via licensed **IDRA** partners (corporate group plans + bKash/telco micro-health riders) backed by real policy-document RAG (`pgvector` over actual PDF policy wordings & exclusions)—never unverified retail solicitation.

---

## 8. Closed Clinical Pilot, 6-Month Roadmap, KPIs & Risk Register

### 7.1 Phased 6-Month Rollout Schedule
| Timeline | Phase & Focus | Key Milestones | Success KPIs |
| :--- | :--- | :--- | :--- |
| **Month 1 (Weeks 1–4)** | **Security, PDPA & Eval Foundation** | Postgres RLS + KMS encryption + SSL Wireless OTP; full **20k+ DGDA catalog** sync; assemble 120-Rx + 100-audio `evals/` benchmark; launch **WhatsApp Companion Bot** beta | `evals/` Generic F1 ≥ 95%; Red-Flag Recall = 100%; PDPA consent flow audited |
| **Month 2 (Weeks 5–8)** | **Closed Clinical Pilot (Dhaka)** | Onboard **50–100 chronic-care families** + **5–10 BMDC physicians** reviewing 1-page Doctor Briefs during real visits; migrate queues to Redis + ARQ + S3/R2 | Doctor Brief usefulness rating **≥ 4.3 / 5**; 30-day caregiver retention **≥ 45%**; zero critical safety incidents |
| **Months 3–4** | **Paid Consumer Launch + GPU Scale** | Launch **bKash / Nagad / SSLCommerz** (`BDT 299/mo`) & **Stripe Diaspora** (`$4.99/mo`); stand up managed L4/A10G **vLLM + ColPali + `MedGemma`** tier; Opus low-bandwidth audio | **500+ paying families**; variable cost per MAU **≤ BDT 55**; Free→Paid conversion **≥ 6%** |
| **Months 5–6** | **B2B2C Diagnostic Pilot & Dialect ASR** | Sign **2–3 mid-tier diagnostic center pilots** (QR/LIMS integration); ship dialect-tuned Bangla ASR v2 (`BanSpeech`/`RegSpeech12`); add pharmacy refill & telemedicine handoff | **10,000+ monthly reports processed** via B2B2C QR; positive unit contribution margin; regional WER ≤ 12% |

### 7.2 Risk & Mitigation Register

| Risk | Severity | Likelihood | Concrete Mitigation |
| :--- | :---: | :---: | :--- |
| **Handwritten BD Rx Misread (Wrong Drug/Dose)** | Critical | High | Never auto-commit `<0.85` confidence drugs; require 1-tap Human-in-the-Loop confirmation; cross-check against `bd_drug_catalog` + `bd_ddi_rules`; display original cropped Rx snippet beside extracted text. |
| **BMDC / Clinical Liability for Bad Medical Advice** | Critical | Medium | Strict non-diagnostic CDS framing; ban arbitrary `%` disease predictions & med-change instructions; enforce deterministic red-flag overrides (`999` / ER); maintain BMDC clinician advisory sign-off & E&O liability cover before commercial launch. |
| **PDPA 2026 Regulatory Audit / Breach** | High | Medium | Local `MedGemma` PII redaction prior to cloud calls; Vertex Asia-South ZDR; Postgres RLS; KMS envelope encryption; automated DSAR deletion + bilingual consent audit trail. |
| **Low Consumer Willingness-to-Pay in Bangladesh** | High | High | Target caregivers & NRB diaspora (`BDT 299` / `$4.99`) rather than price-sensitive mass consumers; use B2B2C diagnostic center QR fees (`BDT 10–15/report`) to subsidize free B2C acquisition. |
| **Bangladesh Bank USD FX Limits for Cloud AI APIs** | Medium | High | Hybrid routing keeps ASR, `BGE-M3`, `Qwen3-Reranker`, and PII/triage on self-hosted/BD-invoiced GPU compute, cutting USD API burn by 60–75%. |
| **Incumbent Response (Arogga, DocTime, Praava)** | Medium | Medium | Incumbents optimize for one-off medicine delivery or single tele-consults; MediTrackAI's moat is **cross-hospital, cross-doctor longitudinal memory** + **Bangla voice caregiver loops** + **1-page Doctor Brief** portable to *any* chamber. |
