import asyncio
import os
import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai_core.pipelines.brief_dag import run_brief_dag
from ai_core.rag.retriever import retrieve_hybrid_context
from ai_core.router import get_ai_provider
from clinical.drug_verifier import verify_medicines
from clinical.red_flag_gate import evaluate_lab_red_flags, evaluate_text_red_flags
from clinical.risk_calculators import calculate_ckd_epi_egfr
from clinical.unit_normalizer import normalize_lab_metrics
from db.database import SessionLocal
from db.models import PatientProfile, User
from main import app

client = TestClient(app)


def test_health_and_unauthenticated_isolation():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"

    # Protected routes and PHI files must reject unauthenticated requests
    assert client.get("/checkins/summaries").status_code == 401
    assert client.get("/uploads/some-profile/demo/lab_may.txt").status_code == 401


def test_cross_tenant_profile_isolation():
    demo = client.post("/api/auth/demo-login")
    assert demo.status_code == 200
    demo_data = demo.json()
    abbu = next(p for p in demo_data["profiles"] if "Abbu" in p["display_name"])

    # Register a separate second user
    uniq = uuid.uuid4().hex[:8]
    reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Other User",
            "email": f"other_{uniq}@example.com",
            "password": "Password123!",
            "accepted_cloud_ai_processing": True,
        },
    )
    assert reg.status_code == 201
    other_token = reg.json()["access_token"]

    # Attempting to access Abbu's profile via X-Profile-Id from other user must return 403
    r = client.get(
        "/api/reports/trends",
        headers={"Authorization": f"Bearer {other_token}", "X-Profile-Id": abbu["id"]},
    )
    assert r.status_code == 403


def test_bd_drug_fuzzy_typo_and_duplicate_ppi():
    db = SessionLocal()
    try:
        res = verify_medicines(
            [
                {"name": "Seclo", "dosage": "20mg", "frequency": "1+0+1"},
                {"name": "Sergal", "dosage": "20mg", "frequency": "1+0+1"},  # deliberate typo
            ],
            db,
        )
        brands = [m["brand_name"] for m in res["medicines"]]
        assert "Seclo" in brands
        assert "Sergel" in brands
        assert any(a["rule_type"] == "duplicate_class" for a in res["ddi_alerts"])
    finally:
        db.close()


def test_loinc_mmol_normalization_and_ckd_epi_guard():
    db = SessionLocal()
    try:
        norm = normalize_lab_metrics(
            [
                {"test_name": "FBS", "value": "140.5", "unit": "mg/dL"},
                {"test_name": "Creatinine", "value": "110.5", "unit": "umol/L"},
            ],
            db,
            sex="M",
        )
        fbs = norm[0]
        creat = norm[1]
        assert fbs.loinc_code == "1558-6"
        assert fbs.canonical_unit == "mmol/L"
        assert 7.7 <= (fbs.canonical_value or 0) <= 7.9
        assert creat.loinc_code == "2160-0"
        assert creat.canonical_unit == "mg/dL"
        assert 1.2 <= (creat.canonical_value or 0) <= 1.3

        egfr_ok = calculate_ckd_epi_egfr(1.48, 62, "M")
        assert egfr_ok["status"] == "computed"
        assert egfr_ok["egfr_ml_min"] is not None

        egfr_missing = calculate_ckd_epi_egfr(None, 62, "M")
        assert egfr_missing["status"] == "insufficient_data"
        assert "serum_creatinine" in egfr_missing["missing_inputs"]
    finally:
        db.close()


def test_dengue_platelets_and_bangla_red_flag_gate():
    lab_alerts = evaluate_lab_red_flags([{"loinc_code": "777-3", "canonical_value": 42000}])
    assert any(a["code"] == "CRITICAL_THROMBOCYTOPENIA" and a["severity"] == "emergency" for a in lab_alerts)

    txt_alerts = evaluate_text_red_flags("আব্বুর সকাল থেকে বুকে ব্যথা আর শ্বাসকষ্ট হচ্ছে")
    codes = {a["code"] for a in txt_alerts}
    assert "CARDIAC_CHEST_PAIN" in codes
    assert "ACUTE_DYSPNEA" in codes


def test_cross_lingual_hybrid_rag_over_abbu():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "demo@meditrack.bd").first()
        abbu = (
            db.query(PatientProfile)
            .filter(PatientProfile.owner_user_id == user.id, PatientProfile.display_name.ilike("%Abbu%"))
            .first()
        )
        trace = asyncio.run(
            retrieve_hybrid_context(db, abbu.id, "abbu er sugar ar gas er osudh ki?", top_k=5)
        )
        assert len(trace.hits) >= 2
        combined = " ".join(h.chunk_text.lower() for h in trace.hits)
        assert ("hba1c" in combined or "glucose" in combined) and ("seclo" in combined or "sergel" in combined)
    finally:
        db.close()


def test_parallel_brief_dag_weasyprint_and_public_qr_route():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "demo@meditrack.bd").first()
        abbu = (
            db.query(PatientProfile)
            .filter(PatientProfile.owner_user_id == user.id, PatientProfile.display_name.ilike("%Abbu%"))
            .first()
        )
        res = asyncio.run(run_brief_dag(db, abbu.id))
        assert res["brief_id"]
        assert os.path.exists(os.path.join("uploads", res["pdf_file_path"]))
        assert os.path.getsize(os.path.join("uploads", res["pdf_file_path"])) > 5000

        pub = client.get(f"/api/public/brief/{res['share_token']}")
        assert pub.status_code == 200
        assert "Abbu" in pub.json()["patient_display_name"]
    finally:
        db.close()


def test_dual_mode_router_graceful_fallback():
    cloud_p = get_ai_provider("cloud")
    assert cloud_p.mode_name == "cloud"
    assert cloud_p.get_telemetry()["inference_mode"] == "cloud"

    gpu_p = get_ai_provider("hybrid_gpu")
    assert gpu_p.mode_name == "hybrid_gpu"
    tel = gpu_p.get_telemetry()
    assert tel["inference_mode"] == "hybrid_gpu"
    # Verify PII redaction works in hybrid_gpu even before Ollama MedGemma weights are pulled
    pii = asyncio.run(gpu_p.redact_pii("My phone is +8801711000111 and Abbu has fever."))
    assert "[PHONE_REDACTED]" in pii.redacted_text
