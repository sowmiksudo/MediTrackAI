from typing import Any, Dict, List, Optional
from rapidfuzz import fuzz
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.models import BdDdiRule, BdDrugCatalog, MedicationEpisode


def _tier_from_conf(conf: float) -> str:
    if conf >= 0.85:
        return "auto_matched"
    if conf >= 0.60:
        return "amber_confirm"
    return "red_manual"


def lookup_bd_drug(query: str, db: Session, limit: int = 5) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    # Clean dosage tokens like "20mg" or "500" for brand similarity matching
    brand_token = q.split()[0] if q.split() else q

    sql = text(
        """
        SELECT id, brand_name, generic_name, strength, dosage_form, manufacturer,
               indicative_price_bdt, atc_code, drug_class,
               GREATEST(
                   similarity(LOWER(brand_name), LOWER(:q)),
                   similarity(LOWER(brand_name), LOWER(:brand_tok)),
                   similarity(LOWER(generic_name), LOWER(:q))
               ) AS sim
        FROM bd_drug_catalog
        WHERE brand_name % :brand_tok
           OR brand_name ILIKE :ilike_q
           OR generic_name ILIKE :ilike_q
        ORDER BY sim DESC, brand_name ASC
        LIMIT :lim
        """
    )
    rows = db.execute(
        sql,
        {"q": q, "brand_tok": brand_token, "ilike_q": f"%{brand_token}%", "lim": limit},
    ).mappings().all()

    results = []
    for r in rows:
        # Boost exact prefix/ratio accuracy with rapidfuzz
        rf_brand = fuzz.WRatio(brand_token.lower(), r["brand_name"].lower()) / 100.0
        rf_full = fuzz.WRatio(q.lower(), f"{r['brand_name']} {r['strength']}".lower()) / 100.0
        conf = round(max(float(r["sim"] or 0.0), rf_brand, rf_full), 3)
        results.append(
            {
                "id": r["id"],
                "brand_name": r["brand_name"],
                "generic_name": r["generic_name"],
                "strength": r["strength"],
                "dosage_form": r["dosage_form"],
                "manufacturer": r["manufacturer"],
                "indicative_price_bdt": r["indicative_price_bdt"],
                "atc_code": r["atc_code"],
                "drug_class": r["drug_class"],
                "confidence": min(1.0, conf),
            }
        )

    if not results:
        # Fallback pure Python rapidfuzz over catalog if pg_trgm threshold missed short names
        all_drugs = db.query(BdDrugCatalog).all()
        scored = []
        for d in all_drugs:
            score = fuzz.WRatio(brand_token.lower(), d.brand_name.lower()) / 100.0
            if score >= 0.50:
                scored.append((score, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, d in scored[:limit]:
            results.append(
                {
                    "id": d.id,
                    "brand_name": d.brand_name,
                    "generic_name": d.generic_name,
                    "strength": d.strength,
                    "dosage_form": d.dosage_form,
                    "manufacturer": d.manufacturer,
                    "indicative_price_bdt": d.indicative_price_bdt,
                    "atc_code": d.atc_code,
                    "drug_class": d.drug_class,
                    "confidence": round(score, 3),
                }
            )
    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results[:limit]


def verify_medicines(
    raw_medicines: List[Dict[str, Any]],
    db: Session,
    patient_profile_id: Optional[Any] = None,
) -> Dict[str, Any]:
    verified_items: List[Dict[str, Any]] = []
    generics_in_rx: List[Dict[str, Any]] = []

    for med in raw_medicines:
        raw_name = str(med.get("name") or "").strip()
        dosage = str(med.get("dosage") or "").strip()
        query = f"{raw_name} {dosage}".strip()
        matches = lookup_bd_drug(query, db, limit=3)

        top = matches[0] if matches else None
        conf = float(top["confidence"]) if top else 0.0
        tier = _tier_from_conf(conf)

        verified_item = {
            "raw_name": raw_name,
            "dosage": dosage or (top["strength"] if top else ""),
            "frequency_bd": med.get("frequency") or med.get("frequency_bd") or "",
            "duration": med.get("duration") or "",
            "special_instructions": med.get("special_instructions") or "",
            "matched_drug_id": top["id"] if top and conf >= 0.60 else None,
            "brand_name": top["brand_name"] if top and conf >= 0.60 else raw_name,
            "generic_name": top["generic_name"] if top and conf >= 0.60 else None,
            "drug_class": top["drug_class"] if top and conf >= 0.60 else None,
            "indicative_price_bdt": top["indicative_price_bdt"] if top and conf >= 0.60 else None,
            "confidence": round(conf, 3),
            "confidence_tier": tier,
            "needs_user_confirm": conf < 0.85,
            "suggestions": matches,
        }
        verified_items.append(verified_item)
        if verified_item["generic_name"]:
            generics_in_rx.append(verified_item)

    # Combine with active medications from the patient's vault for cross-prescription checking
    active_meds: List[Dict[str, Any]] = []
    if patient_profile_id is not None:
        eps = (
            db.query(MedicationEpisode)
            .filter(
                MedicationEpisode.patient_profile_id == patient_profile_id,
                MedicationEpisode.status == "active",
            )
            .all()
        )
        for ep in eps:
            if ep.generic_name:
                active_meds.append(
                    {
                        "brand_name": ep.raw_brand_name,
                        "generic_name": ep.generic_name,
                        "drug_class": ep.drug_class,
                        "source": "active_vault",
                    }
                )

    alerts = check_ddi_and_duplicates(generics_in_rx, active_meds, db)
    needs_review = any(item["needs_user_confirm"] for item in verified_items) or any(
        a["severity"] == "critical" for a in alerts
    )
    avg_conf = round(
        sum(i["confidence"] for i in verified_items) / len(verified_items), 3
    ) if verified_items else 0.0

    return {
        "medicines": verified_items,
        "ddi_alerts": alerts,
        "overall_confidence": avg_conf,
        "needs_review": needs_review,
    }


def check_ddi_and_duplicates(
    new_items: List[Dict[str, Any]],
    existing_items: List[Dict[str, Any]],
    db: Session,
) -> List[Dict[str, Any]]:
    rules = db.query(BdDdiRule).all()
    all_items = [
        {"brand_name": x.get("brand_name") or x.get("raw_name"), "generic_name": x["generic_name"], "source": "current_rx"}
        for x in new_items
        if x.get("generic_name")
    ] + [
        {"brand_name": x["brand_name"], "generic_name": x["generic_name"], "source": "active_vault"}
        for x in existing_items
        if x.get("generic_name")
    ]

    alerts: List[Dict[str, Any]] = []
    seen_keys = set()

    for i in range(len(all_items)):
        for j in range(i + 1, len(all_items)):
            a = all_items[i]
            b = all_items[j]
            # At least one must come from new_items when checking an upload, unless both are in new_items
            if a["source"] == "active_vault" and b["source"] == "active_vault":
                continue
            ga = a["generic_name"].strip()
            gb = b["generic_name"].strip()

            # Check exact duplicate molecule across different brands (e.g. Seclo vs Losectil)
            if ga.lower() == gb.lower() and a["brand_name"].lower() != b["brand_name"].lower():
                key = ("same_generic", tuple(sorted([a["brand_name"].lower(), b["brand_name"].lower()])))
                if key not in seen_keys:
                    seen_keys.add(key)
                    alerts.append(
                        {
                            "rule_type": "duplicate_generic",
                            "severity": "warning",
                            "drugs": [a["brand_name"], b["brand_name"]],
                            "generics": [ga, gb],
                            "clinical_note": f"Duplicate active molecule ({ga}) found across brands {a['brand_name']} and {b['brand_name']}. Verify with prescribing doctor.",
                        }
                    )

            for r in rules:
                ra = r.drug_a_generic.lower()
                rb = r.drug_b_generic.lower()
                if (ga.lower() == ra and gb.lower() == rb) or (ga.lower() == rb and gb.lower() == ra):
                    key = (r.rule_type, tuple(sorted([ga.lower(), gb.lower()])), tuple(sorted([a["brand_name"].lower(), b["brand_name"].lower()])))
                    if key not in seen_keys:
                        seen_keys.add(key)
                        alerts.append(
                            {
                                "rule_type": r.rule_type,
                                "severity": r.severity,
                                "drugs": [a["brand_name"], b["brand_name"]],
                                "generics": [ga, gb],
                                "clinical_note": r.clinical_note,
                            }
                        )
    return alerts
