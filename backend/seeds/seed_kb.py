import json
from pathlib import Path
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import BdDdiRule, BdDrugCatalog, LoincLabReference

SEEDS_DIR = Path(__file__).resolve().parent


def seed_kb(db: Session) -> dict:
    drugs_raw = json.loads((SEEDS_DIR / "bd_drugs_mvp.json").read_text(encoding="utf-8"))
    ddi_raw = json.loads((SEEDS_DIR / "bd_ddi_rules_mvp.json").read_text(encoding="utf-8"))
    loinc_raw = json.loads((SEEDS_DIR / "loinc_labs_mvp.json").read_text(encoding="utf-8"))

    drugs_inserted = 0
    for item in drugs_raw:
        existing = (
            db.query(BdDrugCatalog)
            .filter(
                BdDrugCatalog.brand_name == item["brand_name"],
                BdDrugCatalog.strength == item.get("strength", ""),
                BdDrugCatalog.dosage_form == item.get("dosage_form", "Tablet"),
            )
            .first()
        )
        if existing:
            for k, v in item.items():
                setattr(existing, k, v)
        else:
            db.add(BdDrugCatalog(**item))
            drugs_inserted += 1

    ddis_inserted = 0
    for item in ddi_raw:
        existing = (
            db.query(BdDdiRule)
            .filter(
                BdDdiRule.drug_a_generic == item["drug_a_generic"],
                BdDdiRule.drug_b_generic == item["drug_b_generic"],
                BdDdiRule.rule_type == item["rule_type"],
            )
            .first()
        )
        if existing:
            existing.severity = item["severity"]
            existing.clinical_note = item["clinical_note"]
        else:
            db.add(BdDdiRule(**item))
            ddis_inserted += 1

    loinc_inserted = 0
    for item in loinc_raw:
        existing = db.query(LoincLabReference).filter(LoincLabReference.loinc_code == item["loinc_code"]).first()
        if existing:
            for k, v in item.items():
                setattr(existing, k, v)
        else:
            db.add(LoincLabReference(**item))
            loinc_inserted += 1

    db.commit()
    return {
        "drugs_total": len(drugs_raw),
        "drugs_inserted": drugs_inserted,
        "ddis_total": len(ddi_raw),
        "ddis_inserted": ddis_inserted,
        "loinc_total": len(loinc_raw),
        "loinc_inserted": loinc_inserted,
    }


def main():
    db = SessionLocal()
    try:
        stats = seed_kb(db)
        print("Seeded BD Clinical KB:", stats)
    finally:
        db.close()


if __name__ == "__main__":
    main()
