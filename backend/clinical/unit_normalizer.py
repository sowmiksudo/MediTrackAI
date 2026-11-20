from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from db.models import LoincLabReference


@dataclass
class NormalizedLabMetric:
    raw_name: str
    raw_value: str
    raw_unit: Optional[str]
    loinc_code: Optional[str]
    canonical_name: str
    canonical_value: Optional[float]
    canonical_unit: Optional[str]
    reference_range: Optional[str]
    flag: str  # low | normal | high | critical | unknown


def _parse_numeric(raw_val: Any) -> Optional[float]:
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)):
        return float(raw_val)
    text = str(raw_val).replace(",", "").strip()
    m = re.search(r"[-+]?\d*\.?\d+", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _match_loinc(test_name: str, refs: List[LoincLabReference]) -> Optional[LoincLabReference]:
    q = (test_name or "").strip().lower()
    if not q:
        return None
    # Pass 1: exact canonical or alias match
    for r in refs:
        if r.canonical_name.lower() == q:
            return r
        for alias in (r.aliases or []):
            if alias.lower() == q:
                return r
    # Pass 2: fuzzy match >= 82
    best_ref = None
    best_score = 0.0
    for r in refs:
        candidates = [r.canonical_name.lower()] + [a.lower() for a in (r.aliases or [])]
        for c in candidates:
            score = max(fuzz.ratio(q, c), fuzz.partial_ratio(q, c) if len(q) >= 4 and len(c) >= 4 else 0)
            if score > best_score:
                best_score = score
                best_ref = r
    return best_ref if best_score >= 82 else None


def normalize_lab_metrics(
    metrics: List[Dict[str, Any]],
    db: Session,
    sex: Optional[str] = None,
) -> List[NormalizedLabMetric]:
    refs = db.query(LoincLabReference).all()
    is_female = (sex or "").strip().upper().startswith("F")
    results: List[NormalizedLabMetric] = []

    for m in metrics:
        raw_name = str(m.get("test_name") or "").strip()
        raw_val_str = str(m.get("value") if m.get("value") is not None else "")
        raw_unit = m.get("unit")
        num_val = _parse_numeric(m.get("value"))

        ref = _match_loinc(raw_name, refs)
        if not ref:
            results.append(
                NormalizedLabMetric(
                    raw_name=raw_name,
                    raw_value=raw_val_str,
                    raw_unit=raw_unit,
                    loinc_code=None,
                    canonical_name=raw_name,
                    canonical_value=num_val,
                    canonical_unit=raw_unit,
                    reference_range=m.get("reference_range"),
                    flag="unknown",
                )
            )
            continue

        canonical_val = num_val
        unit_clean = (raw_unit or "").strip()
        if num_val is not None and unit_clean and unit_clean.lower() != ref.standard_unit.lower():
            for alt_u, rule in (ref.alt_units or {}).items():
                if alt_u.lower() == unit_clean.lower():
                    factor = float(rule.get("factor", 1.0))
                    op = rule.get("op", "mul")
                    canonical_val = round(num_val / factor, 3) if op == "div" else round(num_val * factor, 3)
                    break

        low = ref.ref_low_female if (is_female and ref.ref_low_female is not None) else ref.ref_low_male
        high = ref.ref_high_female if (is_female and ref.ref_high_female is not None) else ref.ref_high_male
        ref_range_str = f"{low} - {high} {ref.standard_unit}" if (low is not None and high is not None) else m.get("reference_range")

        flag = "unknown"
        if canonical_val is not None:
            if (ref.critical_low is not None and canonical_val <= ref.critical_low) or (
                ref.critical_high is not None and canonical_val >= ref.critical_high
            ):
                flag = "critical"
            elif low is not None and canonical_val < low:
                flag = "low"
            elif high is not None and canonical_val > high:
                flag = "high"
            else:
                flag = "normal"

        results.append(
            NormalizedLabMetric(
                raw_name=raw_name,
                raw_value=raw_val_str,
                raw_unit=raw_unit,
                loinc_code=ref.loinc_code,
                canonical_name=ref.canonical_name,
                canonical_value=canonical_val,
                canonical_unit=ref.standard_unit,
                reference_range=ref_range_str,
                flag=flag,
            )
        )
    return results
