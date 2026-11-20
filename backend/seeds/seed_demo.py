import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from ai_core.rag.indexer import add_clinical_edge, index_knowledge_chunk
from auth.security import hash_password
from clinical.drug_verifier import verify_medicines
from clinical.risk_calculators import compute_deterministic_clinical_scores
from clinical.unit_normalizer import normalize_lab_metrics
from db.database import SessionLocal
from db.models import (
    CheckIn,
    ClinicalObservation,
    MedicationEpisode,
    PatientProfile,
    PdpaConsent,
    Prescription,
    Report,
    User,
)
from seeds.seed_kb import seed_kb


async def seed_demo_async(db: Session) -> dict:
    # Ensure KB seeds exist first
    seed_kb(db)

    email = "demo@meditrack.bd"
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        profiles = db.query(PatientProfile).filter(PatientProfile.owner_user_id == existing_user.id).all()
        return {
            "status": "already_exists",
            "email": email,
            "profiles": [p.display_name for p in profiles],
        }

    user = User(
        email=email,
        phone_e164="+8801711000111",
        password_hash=hash_password("MediTrack2026!"),
        full_name="Sadia Rahman",
    )
    db.add(user)
    db.flush()

    now = datetime.now(timezone.utc)

    # 1) Self profile
    p_self = PatientProfile(
        owner_user_id=user.id,
        display_name="Self (Sadia)",
        relationship_type="self",
        date_of_birth=date(1994, 5, 14),
        sex="F",
        chronic_conditions=["Allergic Rhinitis"],
        allergies=[],
        emergency_contact_phone="+8801711000112",
    )
    # 2) Abbu profile (Flagship Demo Chronic Patient)
    p_abbu = PatientProfile(
        owner_user_id=user.id,
        display_name="Abbu (Abdul Karim)",
        relationship_type="parent",
        date_of_birth=date(1964, 3, 10),
        sex="M",
        chronic_conditions=["Type 2 Diabetes Mellitus", "Hypertension", "Early CKD Monitoring"],
        allergies=["Penicillin"],
        emergency_contact_phone="+8801711000111",
    )
    # 3) Ammu profile
    p_ammu = PatientProfile(
        owner_user_id=user.id,
        display_name="Ammu (Rehana Begum)",
        relationship_type="parent",
        date_of_birth=date(1970, 8, 22),
        sex="F",
        chronic_conditions=["Hypothyroidism", "Knee Osteoarthritis"],
        allergies=[],
        emergency_contact_phone="+8801711000111",
    )
    db.add_all([p_self, p_abbu, p_ammu])
    db.flush()

    for p in (p_self, p_abbu, p_ammu):
        db.add(
            PdpaConsent(
                user_id=user.id,
                patient_profile_id=p.id,
                consent_version="bd-pdpa-2026-v1",
                accepted_local_storage=True,
                accepted_cloud_ai_processing=True,
            )
        )
    db.commit()

    # Create sample placeholder file markers (no raw PHI exposed publicly)
    demo_dir = Path("uploads") / str(p_abbu.id) / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)
    for fn in ("rx_cardio.txt", "rx_gastric.txt", "lab_may.txt", "lab_aug.txt", "lab_nov.txt"):
        (demo_dir / fn).write_text(f"Demo placeholder for {fn}\n", encoding="utf-8")

    # ---- ABBU: 3 Longitudinal Lab Reports (mmol/L & mg/dL mixed) ----
    lab_batches = [
        (
            "Popular Diagnostic Centre, Dhanmondi",
            (now - timedelta(days=165)).strftime("%Y-%m-%d"),
            now - timedelta(days=165),
            "lab_may.txt",
            [
                {"test_name": "Fasting Blood Glucose", "value": "6.4", "unit": "mmol/L"},
                {"test_name": "HbA1c", "value": "6.9", "unit": "%"},
                {"test_name": "Serum Creatinine", "value": "1.05", "unit": "mg/dL"},
                {"test_name": "Hemoglobin", "value": "13.8", "unit": "g/dL"},
            ],
            "Mildly elevated glycemic baseline; normal renal creatinine.",
        ),
        (
            "Ibn Sina Diagnostic, Dhanmondi",
            (now - timedelta(days=80)).strftime("%Y-%m-%d"),
            now - timedelta(days=80),
            "lab_aug.txt",
            [
                {"test_name": "Fasting Blood Glucose", "value": "140.5", "unit": "mg/dL"},  # Normalizes to ~7.8 mmol/L!
                {"test_name": "HbA1c", "value": "7.6", "unit": "%"},
                {"test_name": "Serum Creatinine", "value": "110.5", "unit": "umol/L"},  # Normalizes to ~1.25 mg/dL!
                {"test_name": "LDL Cholesterol", "value": "132", "unit": "mg/dL"},
            ],
            "Upward glycemic trend (Fasting Glucose reported in mg/dL -> normalized to 7.8 mmol/L) and rising creatinine.",
        ),
        (
            "Labaid Diagnostic, Dhaka",
            (now - timedelta(days=6)).strftime("%Y-%m-%d"),
            now - timedelta(days=6),
            "lab_nov.txt",
            [
                {"test_name": "Fasting Blood Glucose", "value": "9.1", "unit": "mmol/L"},
                {"test_name": "HbA1c", "value": "8.4", "unit": "%"},
                {"test_name": "Serum Creatinine", "value": "1.48", "unit": "mg/dL"},
                {"test_name": "Platelets", "value": "195000", "unit": "/uL"},
                {"test_name": "Serum Potassium", "value": "4.6", "unit": "mmol/L"},
            ],
            "Recent Labaid panel shows worsened glycemic control (HbA1c 8.4%) and rising creatinine (1.48 mg/dL).",
        ),
    ]

    for lab_name, r_date, r_dt, fname, metrics, overview in lab_batches:
        norm = normalize_lab_metrics(metrics, db, sex="M")
        latest_map = {n.loinc_code: n.canonical_value for n in norm if n.loinc_code and n.canonical_value is not None}
        det = compute_deterministic_clinical_scores(latest_map, p_abbu.date_of_birth, "M")
        rep = Report(
            patient_profile_id=p_abbu.id,
            file_path=str(Path(str(p_abbu.id)) / "demo" / fname),
            lab_name=lab_name,
            report_date=r_date,
            raw_ocr_text=overview,
            extracted_json={"lab_name": lab_name, "report_date": r_date},
            verification_status="confirmed",
            critical_alerts=[],
            lab_summary_overview=overview,
            deterministic_scores=det,
            created_at=r_dt,
        )
        db.add(rep)
        db.flush()

        for n in norm:
            db.add(
                ClinicalObservation(
                    patient_profile_id=p_abbu.id,
                    source_type="lab",
                    source_id=rep.id,
                    loinc_code=n.loinc_code,
                    raw_name=n.raw_name,
                    raw_value=n.raw_value,
                    raw_unit=n.raw_unit,
                    canonical_value=n.canonical_value,
                    canonical_unit=n.canonical_unit,
                    reference_range=n.reference_range,
                    flag=n.flag,
                    observed_at=r_dt,
                )
            )
        if det["egfr_ckd_epi"].get("status") == "computed":
            egfr_val = det["egfr_ckd_epi"]["egfr_ml_min"]
            db.add(
                ClinicalObservation(
                    patient_profile_id=p_abbu.id,
                    source_type="lab",
                    source_id=rep.id,
                    loinc_code="98979-8",
                    raw_name="eGFR (CKD-EPI 2021)",
                    raw_value=str(egfr_val),
                    raw_unit="mL/min/1.73m2",
                    canonical_value=egfr_val,
                    canonical_unit="mL/min/1.73m2",
                    reference_range="90.0 - 140.0 mL/min/1.73m2",
                    flag="low" if egfr_val < 60 else "normal",
                    observed_at=r_dt,
                )
            )
        db.commit()

        metric_txt = "; ".join(f"{n.canonical_name}: {n.canonical_value} {n.canonical_unit} ({n.flag})" for n in norm)
        await index_knowledge_chunk(
            db=db,
            patient_profile_id=p_abbu.id,
            source_type="lab_report",
            source_id=str(rep.id),
            chunk_text=f"Lab Report ({lab_name}) on {r_date}: {metric_txt}. {overview}",
            event_at=r_dt,
            language="en",
        )

    # ---- ABBU: 2 BD Prescriptions with Live Duplicate PPI Alert (Seclo + Sergel) ----
    rx1_dt = now - timedelta(days=45)
    rx1_meds = [
        {"name": "Comet", "dosage": "500mg", "frequency": "1+0+1", "duration": "ongoing", "special_instructions": "After meals"},
        {"name": "Bizoran", "dosage": "5mg+20mg", "frequency": "0+0+1", "duration": "ongoing", "special_instructions": "Night"},
        {"name": "Ecosprin", "dosage": "75mg", "frequency": "0+1+0", "duration": "ongoing", "special_instructions": "After lunch"},
        {"name": "Seclo", "dosage": "20mg", "frequency": "1+0+1", "duration": "30 days", "special_instructions": "Before meals"},
    ]
    v1 = verify_medicines(rx1_meds, db, patient_profile_id=p_abbu.id)
    rx1 = Prescription(
        patient_profile_id=p_abbu.id,
        file_path=str(Path(str(p_abbu.id)) / "demo" / "rx_cardio.txt"),
        doc_date=rx1_dt.strftime("%Y-%m-%d"),
        doctor_name="Prof. Dr. Mahmudul Hasan",
        doctor_qualification="MBBS, FCPS (Medicine), MD (Cardiology)",
        doctor_bmdc_reg="A-34812",
        hospital="Square Hospital Dhaka",
        diagnosis="Type 2 Diabetes & Essential Hypertension",
        prescription_summary="Maintenance T2DM & HTN regimen (Comet 500mg, Bizoran 5/20, Ecosprin 75mg) plus Seclo 20mg for gastric protection.",
        verification_status="confirmed",
        overall_confidence=v1["overall_confidence"],
        ddi_alerts=v1["ddi_alerts"],
        extracted_json={"medicines": v1["medicines"]},
        created_at=rx1_dt,
    )
    db.add(rx1)
    db.flush()
    for item in v1["medicines"]:
        db.add(
            MedicationEpisode(
                patient_profile_id=p_abbu.id,
                prescription_id=rx1.id,
                raw_brand_name=item["raw_name"],
                matched_drug_id=item["matched_drug_id"],
                generic_name=item["generic_name"],
                drug_class=item["drug_class"],
                dosage=item["dosage"],
                frequency_bd=item["frequency_bd"],
                special_instructions=item["special_instructions"],
                match_confidence=item["confidence"],
                needs_user_confirm=False,
                status="active",
                started_at=rx1_dt,
            )
        )
    db.commit()
    await index_knowledge_chunk(
        db=db,
        patient_profile_id=p_abbu.id,
        source_type="prescription",
        source_id=str(rx1.id),
        chunk_text=f"Prescription on {rx1.doc_date} by {rx1.doctor_name} (Square Hospital Dhaka): Comet 500mg (Metformin) 1+0+1, Bizoran 5/20 (Amlodipine+Olmesartan) 0+0+1, Ecosprin 75mg (Aspirin), Seclo 20mg (Omeprazole) 1+0+1.",
        event_at=rx1_dt,
        language="en",
    )

    # Rx 2 from a second doctor adds Sergel 20mg -> Duplicate PPI alert with Seclo!
    rx2_dt = now - timedelta(days=10)
    rx2_meds = [
        {"name": "Sergel", "dosage": "20mg", "frequency": "1+0+1", "duration": "14 days", "special_instructions": "30 min before breakfast & dinner"},
        {"name": "Rosuva", "dosage": "10mg", "frequency": "0+0+1", "duration": "ongoing", "special_instructions": "Bedtime"},
    ]
    v2 = verify_medicines(rx2_meds, db, patient_profile_id=p_abbu.id)
    rx2 = Prescription(
        patient_profile_id=p_abbu.id,
        file_path=str(Path(str(p_abbu.id)) / "demo" / "rx_gastric.txt"),
        doc_date=rx2_dt.strftime("%Y-%m-%d"),
        doctor_name="Dr. Farhana Yasmin",
        doctor_qualification="MBBS, MD (Gastroenterology)",
        doctor_bmdc_reg="A-49201",
        hospital="Popular Medical College Hospital, Dhanmondi",
        diagnosis="Acid Reflux / Dyspepsia",
        prescription_summary="Added Sergel 20mg (Esomeprazole) and Rosuva 10mg; flagged duplicate PPI therapy alongside active Seclo 20mg (Omeprazole).",
        verification_status="pending_review",
        overall_confidence=v2["overall_confidence"],
        ddi_alerts=v2["ddi_alerts"],
        extracted_json={"medicines": v2["medicines"], "ddi_alerts": v2["ddi_alerts"]},
        created_at=rx2_dt,
    )
    db.add(rx2)
    db.flush()
    for item in v2["medicines"]:
        db.add(
            MedicationEpisode(
                patient_profile_id=p_abbu.id,
                prescription_id=rx2.id,
                raw_brand_name=item["raw_name"],
                matched_drug_id=item["matched_drug_id"],
                generic_name=item["generic_name"],
                drug_class=item["drug_class"],
                dosage=item["dosage"],
                frequency_bd=item["frequency_bd"],
                special_instructions=item["special_instructions"],
                match_confidence=item["confidence"],
                needs_user_confirm=item["needs_user_confirm"],
                status="active",
                started_at=rx2_dt,
            )
        )
    for alert in v2["ddi_alerts"]:
        add_clinical_edge(db, p_abbu.id, "prescription", str(rx2.id), "TRIGGERED_ALERT", "ddi_rule", alert["rule_type"], alert)
    db.commit()
    await index_knowledge_chunk(
        db=db,
        patient_profile_id=p_abbu.id,
        source_type="prescription",
        source_id=str(rx2.id),
        chunk_text=f"Prescription on {rx2.doc_date} by {rx2.doctor_name}: Sergel 20mg (Esomeprazole) 1+0+1 and Rosuva 10mg (Rosuvastatin). Alert: Duplicate PPI therapy with existing Seclo 20mg (Omeprazole).",
        event_at=rx2_dt,
        language="en",
    )

    # ---- ABBU: 2 Banglish / Bangla Check-ins ----
    ci1_dt = now - timedelta(days=12)
    ci1 = CheckIn(
        patient_profile_id=p_abbu.id,
        transcript={"turns": [{"role": "user", "text": "Abbur rater dike ghum kom hocche, gas er jonno Seclo ar notun kore Sergel khacche."}]},
        summary="Abbu experiencing mild nocturnal acidity and reduced sleep; currently taking both Seclo and Sergel concurrently.",
        mood="Tired",
        symptoms=["Acidity", "Poor sleep"],
        medications_mentioned=["Seclo 20mg", "Sergel 20mg"],
        sleep_quality="Fair",
        energy_level="Moderate",
        concerns=["Concurrent dual PPI intake (Seclo + Sergel)"],
        ai_insights=["Discuss overlapping Seclo & Sergel capsules at next doctor visit."],
        overall_score="neutral",
        language_detected="bn-en",
        created_at=ci1_dt,
    )
    ci2_dt = now - timedelta(days=2)
    ci2 = CheckIn(
        patient_profile_id=p_abbu.id,
        transcript={"turns": [{"role": "user", "text": "আজকে সকাল থেকে আব্বুর মাথা একটু ঘুরাচ্ছে, fasting sugar 9.1 আসছিল আর পায়ে হালকা ফোলা।"}]},
        summary="Patient reports mild morning dizziness and mild ankle swelling after recent Fasting Glucose 9.1 mmol/L.",
        mood="Anxious",
        symptoms=["Morning dizziness", "Mild ankle swelling", "Fatigue"],
        medications_mentioned=["Comet 500mg", "Bizoran 5/20"],
        sleep_quality="Disturbed",
        energy_level="Low",
        concerns=["Elevated Fasting Glucose 9.1 mmol/L", "Rising Serum Creatinine 1.48 mg/dL", "Mild pedal edema"],
        ai_insights=["Bring Labaid creatinine & HbA1c trend to doctor soon.", "Monitor blood pressure and ankle swelling daily."],
        overall_score="negative",
        language_detected="bn-en",
        created_at=ci2_dt,
    )
    db.add_all([ci1, ci2])
    db.commit()
    db.refresh(ci1)
    db.refresh(ci2)

    await index_knowledge_chunk(
        db=db,
        patient_profile_id=p_abbu.id,
        source_type="checkin",
        source_id=str(ci1.id),
        chunk_text=f"Banglish Check-In ({ci1_dt.strftime('%Y-%m-%d')}): {ci1.summary}",
        event_at=ci1_dt,
        language="bn-en",
    )
    await index_knowledge_chunk(
        db=db,
        patient_profile_id=p_abbu.id,
        source_type="checkin",
        source_id=str(ci2.id),
        chunk_text=f"Bangla Check-In ({ci2_dt.strftime('%Y-%m-%d')}): {ci2.summary} Symptoms: Morning dizziness, mild ankle swelling.",
        event_at=ci2_dt,
        language="bn-en",
    )

    # ---- AMMU: Quick Thyroid Seed ----
    ammu_meds = verify_medicines([{"name": "Thyrox", "dosage": "50mcg", "frequency": "1+0+0"}], db, patient_profile_id=p_ammu.id)
    rx_ammu = Prescription(
        patient_profile_id=p_ammu.id,
        file_path=str(Path(str(p_ammu.id)) / "demo" / "rx_cardio.txt"),
        doc_date=(now - timedelta(days=20)).strftime("%Y-%m-%d"),
        doctor_name="Dr. Taslima Akter",
        hospital="Evercare Hospital Dhaka",
        diagnosis="Primary Hypothyroidism",
        prescription_summary="Thyrox 50mcg once daily empty stomach in the morning.",
        verification_status="confirmed",
        overall_confidence=ammu_meds["overall_confidence"],
        ddi_alerts=[],
        extracted_json={"medicines": ammu_meds["medicines"]},
    )
    db.add(rx_ammu)
    db.flush()
    for item in ammu_meds["medicines"]:
        db.add(
            MedicationEpisode(
                patient_profile_id=p_ammu.id,
                prescription_id=rx_ammu.id,
                raw_brand_name=item["raw_name"],
                matched_drug_id=item["matched_drug_id"],
                generic_name=item["generic_name"],
                drug_class=item["drug_class"],
                dosage=item["dosage"],
                frequency_bd=item["frequency_bd"],
                match_confidence=item["confidence"],
                needs_user_confirm=False,
                status="active",
            )
        )
    db.commit()
    await index_knowledge_chunk(
        db=db,
        patient_profile_id=p_ammu.id,
        source_type="prescription",
        source_id=str(rx_ammu.id),
        chunk_text="Ammu Prescription: Thyrox 50mcg (Levothyroxine) once daily on empty stomach for Hypothyroidism.",
        event_at=now - timedelta(days=20),
        language="en",
    )

    return {
        "status": "seeded",
        "email": email,
        "profiles": [p_self.display_name, p_abbu.display_name, p_ammu.display_name],
        "abbu_ddi_alerts": v2["ddi_alerts"],
    }


def main():
    db = SessionLocal()
    try:
        res = asyncio.run(seed_demo_async(db))
        print("Seeded Dhaka Family Demo:", res)
    finally:
        db.close()


if __name__ == "__main__":
    main()
