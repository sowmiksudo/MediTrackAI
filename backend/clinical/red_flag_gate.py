from typing import Any, Dict, List


SYMPTOM_RED_FLAGS = [
    {
        "code": "CARDIAC_CHEST_PAIN",
        "severity": "emergency",
        "keywords": ["chest pain", "chest tightness", "বুকে ব্যথা", "বুকে চাপ", "buke byatha", "buke chap", "left arm pain"],
        "title": "Possible Cardiac Emergency (Chest Pain / Pressure)",
        "action": "Seek emergency medical care immediately or call Bangladesh National Emergency 999.",
    },
    {
        "code": "ACUTE_DYSPNEA",
        "severity": "emergency",
        "keywords": ["shortness of breath", "difficulty breathing", "can't breathe", "শ্বাসকষ্ট", "shashkosto", "dum bondho"],
        "title": "Acute Breathing Difficulty",
        "action": "Go to the nearest hospital Emergency Department immediately or call 999.",
    },
    {
        "code": "STROKE_SIGNS",
        "severity": "emergency",
        "keywords": ["slurred speech", "face drooping", "one side weak", "মুখ বেঁকে", "এক পাশ অবশ", "অজ্ঞান", "unconscious", "seizure"],
        "title": "Possible Stroke / Neurological Emergency",
        "action": "Time-critical emergency — go to an ER immediately or call 999.",
    },
    {
        "code": "GI_BLEED_OR_DENGUE_WARNING",
        "severity": "emergency",
        "keywords": ["blood vomit", "black stool", "রক্ত বমি", "কালো পায়খানা", "kalo paykhana", "bleeding gums", "rokto pora"],
        "title": "Bleeding / Severe Dengue Warning Sign",
        "action": "Seek urgent Emergency Room evaluation immediately (do NOT take NSAIDs like Naproxen/Diclofenac).",
    },
]


def evaluate_lab_red_flags(observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for obs in observations:
        loinc = obs.get("loinc_code")
        val = obs.get("canonical_value")
        if val is None:
            continue

        if loinc == "777-3":  # Platelets /uL (Crucial for BD Dengue)
            if val < 50000:
                alerts.append(
                    {
                        "code": "CRITICAL_THROMBOCYTOPENIA",
                        "severity": "emergency",
                        "title": f"Critical Low Platelets ({int(val):,} /uL)",
                        "action": "Immediate ER evaluation required (high bleeding risk / severe Dengue warning). Avoid NSAIDs & Aspirin unless directed by physician.",
                        "source": "Platelets",
                    }
                )
            elif val < 100000:
                alerts.append(
                    {
                        "code": "DENGUE_PLATELET_WARNING",
                        "severity": "urgent",
                        "title": f"Low Platelets Alert ({int(val):,} /uL)",
                        "action": "Same-day doctor review & repeat CBC advised. Monitor for fever, abdominal pain, or bleeding.",
                        "source": "Platelets",
                    }
                )
        elif loinc == "2823-3" and (val >= 6.0 or val <= 2.8):
            alerts.append(
                {
                    "code": "CRITICAL_POTASSIUM",
                    "severity": "emergency",
                    "title": f"Critical Serum Potassium ({val} mmol/L)",
                    "action": "Immediate ER / ECG assessment required (arrhythmia risk). Call 999 or visit nearest emergency department.",
                    "source": "Serum Potassium",
                }
            )
        elif loinc in ("1558-6", "2345-7"):
            if val < 3.0:
                alerts.append(
                    {
                        "code": "SEVERE_HYPOGLYCEMIA",
                        "severity": "emergency",
                        "title": f"Severe Hypoglycemia ({val} mmol/L)",
                        "action": "Immediate fast-acting sugar if conscious and urgent medical review.",
                        "source": "Blood Glucose",
                    }
                )
            elif val >= 16.7:
                alerts.append(
                    {
                        "code": "SEVERE_HYPERGLYCEMIA",
                        "severity": "emergency",
                        "title": f"Critical Hyperglycemia ({val} mmol/L)",
                        "action": "Urgent medical evaluation to rule out DKA/HHS; seek immediate care if vomiting or drowsy.",
                        "source": "Blood Glucose",
                    }
                )
        elif loinc == "718-7" and val < 7.0:
            alerts.append(
                {
                    "code": "CRITICAL_ANEMIA",
                    "severity": "emergency",
                    "title": f"Critical Low Hemoglobin ({val} g/dL)",
                    "action": "Immediate hospital evaluation recommended.",
                    "source": "Hemoglobin",
                }
            )
        elif loinc == "98979-8" and val < 30.0:
            alerts.append(
                {
                    "code": "SEVERE_RENAL_IMPAIRMENT",
                    "severity": "urgent",
                    "title": f"Severely Reduced eGFR ({val} mL/min/1.73m2)",
                    "action": "Prompt nephrologist/physician review required; verify Metformin/NSAID safety immediately.",
                    "source": "eGFR",
                }
            )
    return alerts


def evaluate_text_red_flags(text_input: str) -> List[Dict[str, Any]]:
    t = (text_input or "").lower()
    if not t:
        return []
    alerts: List[Dict[str, Any]] = []
    for rule in SYMPTOM_RED_FLAGS:
        if any(kw in t for kw in rule["keywords"]):
            alerts.append(
                {
                    "code": rule["code"],
                    "severity": rule["severity"],
                    "title": rule["title"],
                    "action": rule["action"],
                    "emergency_number": "999",
                    "source": "Voice/Text Check-In",
                }
            )
    return alerts
