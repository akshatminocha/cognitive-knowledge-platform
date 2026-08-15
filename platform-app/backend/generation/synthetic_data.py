"""
Synthetic Data Generator — Generate demo data for each domain schema.

Creates realistic synthetic data for testing and demonstrations:
- CSV files for tabular ingestion
- JSON files for structured ingestion
- Markdown files for unstructured ingestion

Each domain generates data consistent with its ontology schema.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import random
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed data pools
# ---------------------------------------------------------------------------
HEALTHTECH_DATA = {
    "first_names": ["John", "Jane", "Michael", "Sarah", "Robert", "Emily", "David", "Lisa"],
    "last_names": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Davis", "Miller", "Wilson"],
    "specializations": ["Cardiology", "Neurology", "Oncology", "Orthopedics", "Pediatrics", "Dermatology"],
    "diagnoses": [
        ("E11.9", "Type 2 Diabetes Mellitus"),
        ("I10", "Essential Hypertension"),
        ("J45.909", "Unspecified Asthma"),
        ("M54.5", "Low Back Pain"),
        ("F32.9", "Major Depressive Disorder"),
        ("E78.5", "Hyperlipidemia"),
    ],
    "medications": [
        ("Metformin", "500mg", "twice daily"),
        ("Lisinopril", "10mg", "once daily"),
        ("Albuterol", "90mcg", "as needed"),
        ("Ibuprofen", "400mg", "every 6 hours"),
        ("Sertraline", "50mg", "once daily"),
        ("Atorvastatin", "20mg", "once daily at bedtime"),
    ],
    "lab_tests": [
        ("HbA1c", "%", "4.0-5.6"),
        ("Blood Pressure", "mmHg", "< 120/80"),
        ("Total Cholesterol", "mg/dL", "< 200"),
        ("Creatinine", "mg/dL", "0.6-1.2"),
        ("TSH", "mIU/L", "0.4-4.0"),
    ],
}

FINTECH_DATA = {
    "account_types": ["checking", "savings", "investment", "credit"],
    "currencies": ["USD", "EUR", "GBP", "JPY"],
    "transaction_types": ["debit", "credit", "transfer", "payment", "withdrawal"],
    "merchants": [
        ("Amazon", "E-commerce", "US"),
        ("Starbucks", "Food & Beverage", "US"),
        ("Shell", "Fuel", "US"),
        ("Netflix", "Entertainment", "US"),
        ("Whole Foods", "Grocery", "US"),
    ],
    "alert_types": ["fraud", "aml", "compliance", "unusual_activity"],
}


def _rand_id(prefix: str) -> str:
    return f"{prefix}-{str(uuid.uuid4())[:8].upper()}"


def _rand_date(year: int = 2024) -> str:
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------
def generate_healthtech(num_patients: int = 20) -> dict[str, Any]:
    """Generate synthetic healthtech data."""
    data = HEALTHTECH_DATA
    patients = []
    doctors = []
    diagnoses_list = []
    medications_list = []
    lab_results = []
    visits = []

    # Generate doctors
    for i in range(5):
        doctors.append({
            "doctor_id": _rand_id("DOC"),
            "name": f"Dr. {random.choice(data['first_names'])} {random.choice(data['last_names'])}",
            "specialization": data["specializations"][i % len(data["specializations"])],
            "department": "General Medicine",
        })

    # Generate patients and related data
    for i in range(num_patients):
        patient_id = _rand_id("PAT")
        patient = {
            "patient_id": patient_id,
            "name": f"{random.choice(data['first_names'])} {random.choice(data['last_names'])}",
            "date_of_birth": _rand_date(random.randint(1950, 2000)),
            "gender": random.choice(["Male", "Female"]),
            "blood_type": random.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
        }
        patients.append(patient)

        # 1-3 diagnoses per patient
        for _ in range(random.randint(1, 3)):
            icd, name = random.choice(data["diagnoses"])
            diagnoses_list.append({
                "diagnosis_id": _rand_id("DX"),
                "patient_id": patient_id,
                "icd_code": icd,
                "name": name,
                "severity": random.choice(["mild", "moderate", "severe"]),
                "date_diagnosed": _rand_date(),
            })

        # 1-2 medications per patient
        for _ in range(random.randint(1, 2)):
            med_name, dosage, freq = random.choice(data["medications"])
            medications_list.append({
                "medication_id": _rand_id("MED"),
                "patient_id": patient_id,
                "name": med_name,
                "dosage": dosage,
                "frequency": freq,
                "prescribed_by": random.choice(doctors)["doctor_id"],
            })

        # 1-3 lab results per patient
        for _ in range(random.randint(1, 3)):
            test_name, unit, ref_range = random.choice(data["lab_tests"])
            lab_results.append({
                "lab_id": _rand_id("LAB"),
                "patient_id": patient_id,
                "test_name": test_name,
                "value": str(round(random.uniform(2.0, 300.0), 1)),
                "unit": unit,
                "reference_range": ref_range,
                "test_date": _rand_date(),
                "status": random.choice(["Normal", "Abnormal", "Critical"]),
            })

        # 1-2 visits per patient
        for _ in range(random.randint(1, 2)):
            visits.append({
                "visit_id": _rand_id("VIS"),
                "patient_id": patient_id,
                "doctor_id": random.choice(doctors)["doctor_id"],
                "visit_date": _rand_date(),
                "visit_type": random.choice(["Outpatient", "Inpatient", "Emergency"]),
                "chief_complaint": random.choice([
                    "Follow-up visit", "Chest pain", "Routine checkup",
                    "Medication review", "Lab result discussion",
                ]),
            })

    return {
        "patients": patients,
        "doctors": doctors,
        "diagnoses": diagnoses_list,
        "medications": medications_list,
        "lab_results": lab_results,
        "visits": visits,
    }


def generate_fintech(num_customers: int = 15) -> dict[str, Any]:
    """Generate synthetic fintech data."""
    data = FINTECH_DATA
    customers = []
    accounts = []
    transactions = []

    for i in range(num_customers):
        cust_id = _rand_id("CUST")
        customers.append({
            "customer_id": cust_id,
            "name": f"{random.choice(HEALTHTECH_DATA['first_names'])} {random.choice(HEALTHTECH_DATA['last_names'])}",
            "email": f"user{i}@example.com",
            "risk_score": round(random.uniform(0, 100), 1),
            "kyc_status": random.choice(["verified", "pending", "flagged"]),
        })

        # 1-3 accounts per customer
        for _ in range(random.randint(1, 3)):
            acc_id = _rand_id("ACC")
            accounts.append({
                "account_id": acc_id,
                "customer_id": cust_id,
                "account_type": random.choice(data["account_types"]),
                "balance": round(random.uniform(100, 100000), 2),
                "currency": "USD",
                "status": "active",
            })

            # 3-10 transactions per account
            for _ in range(random.randint(3, 10)):
                merch_name, merch_cat, merch_country = random.choice(data["merchants"])
                transactions.append({
                    "transaction_id": _rand_id("TXN"),
                    "account_id": acc_id,
                    "amount": round(random.uniform(5, 5000), 2),
                    "currency": "USD",
                    "transaction_type": random.choice(data["transaction_types"]),
                    "merchant_name": merch_name,
                    "merchant_category": merch_cat,
                    "timestamp": f"{_rand_date()}T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00Z",
                    "risk_flag": random.random() < 0.05,
                })

    return {
        "customers": customers,
        "accounts": accounts,
        "transactions": transactions,
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def _write_csv(rows: list[dict], path: Path) -> None:
    """Write a list of dicts to a CSV file."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"Wrote {len(rows)} rows to {path}")


def _write_json(data: Any, path: Path) -> None:
    """Write data to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Wrote JSON to {path}")


def generate_all(output_dir: Path) -> dict[str, int]:
    """
    Generate all synthetic datasets and write to output_dir.

    Returns a summary of files created.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {}

    # Healthtech
    ht = generate_healthtech(num_patients=20)
    for key, rows in ht.items():
        path = output_dir / "healthtech" / f"{key}.csv"
        _write_csv(rows, path)
        summary[f"healthtech/{key}.csv"] = len(rows)

    _write_json(ht, output_dir / "healthtech" / "healthtech_full.json")

    # Fintech
    ft = generate_fintech(num_customers=15)
    for key, rows in ft.items():
        path = output_dir / "fintech" / f"{key}.csv"
        _write_csv(rows, path)
        summary[f"fintech/{key}.csv"] = len(rows)

    _write_json(ft, output_dir / "fintech" / "fintech_full.json")

    logger.info(f"Generated {len(summary)} synthetic data files")
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    output = Path(__file__).parent.parent.parent / "data" / "synthetic"
    result = generate_all(output)
    print(f"\nGenerated {len(result)} files:")
    for filename, count in result.items():
        print(f"  {filename}: {count} rows")
