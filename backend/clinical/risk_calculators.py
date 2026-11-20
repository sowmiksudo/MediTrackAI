from datetime import date
from typing import Any, Dict, List, Optional


def compute_age_years(dob: Optional[date]) -> Optional[int]:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def calculate_ckd_epi_egfr(
    creatinine_mg_dl: Optional[float],
    age_years: Optional[int],
    sex: Optional[str],
) -> Dict[str, Any]:
    """Deterministic CKD-EPI 2021 Creatinine Equation (race-free)."""
    missing: List[str] = []
    if creatinine_mg_dl is None or creatinine_mg_dl <= 0:
        missing.append("serum_creatinine")
    if age_years is None or age_years < 18:
        missing.append("age_years (>=18)")
    if not sex or sex.strip().upper()[0] not in ("M", "F"):
        missing.append("sex (M/F)")

    if missing:
        return {
            "calculator": "CKD-EPI 2021 eGFR",
            "status": "insufficient_data",
            "missing_inputs": missing,
            "egfr_ml_min": None,
            "kdigo_stage": None,
        }

    is_female = sex.strip().upper().startswith("F")
    kappa = 0.7 if is_female else 0.9
    alpha = -0.241 if is_female else -0.302
    sex_factor = 1.012 if is_female else 1.0

    ratio = creatinine_mg_dl / kappa
    egfr = 142.0 * (min(ratio, 1.0) ** alpha) * (max(ratio, 1.0) ** -1.200) * (0.9938 ** age_years) * sex_factor
    egfr = round(egfr, 1)

    if egfr >= 90:
        stage = "G1 (Normal or High)"
    elif egfr >= 60:
        stage = "G2 (Mildly Decreased)"
    elif egfr >= 45:
        stage = "G3a (Mild-to-Moderate Decrease)"
    elif egfr >= 30:
        stage = "G3b (Moderate-to-Severe Decrease)"
    elif egfr >= 15:
        stage = "G4 (Severely Decreased)"
    else:
        stage = "G5 (Kidney Failure Range)"

    return {
        "calculator": "CKD-EPI 2021 eGFR",
        "status": "computed",
        "missing_inputs": [],
        "egfr_ml_min": egfr,
        "kdigo_stage": stage,
        "metformin_caution": egfr < 45,
        "metformin_contraindicated": egfr < 30,
    }


def classify_ada_glycemic_band(
    hba1c_pct: Optional[float] = None,
    fasting_glucose_mmol: Optional[float] = None,
) -> Dict[str, Any]:
    missing: List[str] = []
    if hba1c_pct is None and fasting_glucose_mmol is None:
        return {
            "calculator": "ADA Glycemic Thresholds",
            "status": "insufficient_data",
            "missing_inputs": ["hba1c_or_fasting_glucose"],
            "band": None,
        }

    band = "Normal Range"
    details: List[str] = []

    if hba1c_pct is not None:
        if hba1c_pct >= 6.5:
            band = "Diabetes-Range Elevation (>= 6.5%)"
        elif hba1c_pct >= 5.7:
            band = "Prediabetes Range (5.7 - 6.4%)"
        details.append(f"HbA1c {hba1c_pct}%")

    if fasting_glucose_mmol is not None:
        if fasting_glucose_mmol >= 7.0:
            band = "Diabetes-Range Elevation (>= 7.0 mmol/L)"
        elif fasting_glucose_mmol >= 5.6 and band == "Normal Range":
            band = "Impaired Fasting Glucose Range (5.6 - 6.9 mmol/L)"
        details.append(f"Fasting Glucose {fasting_glucose_mmol} mmol/L")

    return {
        "calculator": "ADA Glycemic Thresholds",
        "status": "computed",
        "missing_inputs": missing,
        "band": band,
        "summary": "; ".join(details),
    }


def compute_deterministic_clinical_scores(
    latest_by_loinc: Dict[str, float],
    dob: Optional[date],
    sex: Optional[str],
) -> Dict[str, Any]:
    age = compute_age_years(dob)
    egfr = calculate_ckd_epi_egfr(latest_by_loinc.get("2160-0"), age, sex)
    glycemic = classify_ada_glycemic_band(
        hba1c_pct=latest_by_loinc.get("4548-4"),
        fasting_glucose_mmol=latest_by_loinc.get("1558-6"),
    )
    return {
        "egfr_ckd_epi": egfr,
        "glycemic_band": glycemic,
    }
