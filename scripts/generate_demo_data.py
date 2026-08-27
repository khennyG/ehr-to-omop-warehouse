"""Generate a synthetic Synthea-format patient population for local development.

Real Synthea generation needs a JVM and the Synthea jar — see
scripts/generate_synthea_data.py for that path, which this script is not a
replacement for in production. What this script is for: producing the exact
six CSVs src/extract/synthea_loader.py expects (same filenames, same columns,
same dtypes it validates against), with clinically coherent content, wherever
Python runs and nothing else does.

"Clinically coherent" means more than plausible-looking numbers in each
column independently. It means: a patient's conditions start after they're
born and before they die; a diabetes diagnosis precedes the metformin
prescription that treats it; an opioid sequence actually escalates in potency
across the prescriptions that make it up, in order, over realistic gaps; a
polypharmacy patient's five-plus drugs are genuinely overlapping in time, not
just five rows that happen to share a person_id. Those are the properties
src/analytics/cohort_builder.py's temporal logic and the three predefined
cohorts in this project's README actually depend on — a generator that ignored
them would hand the analytics layer nothing real to find.
"""

import uuid
from datetime import date, timedelta
from pathlib import Path

import click
import numpy as np
import pandas as pd
from loguru import logger

from scripts.demo_codes import (
    CONDITION_ASTHMA,
    CONDITION_CAD,
    CONDITION_CKD,
    CONDITION_COPD,
    CONDITION_DIABETES_LEGACY,
    CONDITION_DIABETIC_NEPHROPATHY,
    CONDITION_DIABETIC_RETINOPATHY,
    CONDITION_HEART_FAILURE,
    CONDITION_HYPERLIPIDEMIA,
    CONDITION_HYPERTENSION,
    CONDITION_MI,
    CONDITION_PHARYNGITIS,
    CONDITION_STROKE,
    CONDITION_T2DM,
    DRUG_ALBUTEROL,
    DRUG_AMLODIPINE,
    DRUG_ASPIRIN,
    DRUG_ATORVASTATIN,
    DRUG_HCTZ,
    DRUG_LEVOTHYROXINE,
    DRUG_LISINOPRIL,
    DRUG_METFORMIN,
    DRUG_METFORMIN_BRAND,
    DRUG_OMEPRAZOLE,
    LAB_BMI,
    LAB_DIASTOLIC_BP,
    LAB_GLUCOSE,
    LAB_HBA1C,
    LAB_HEART_RATE,
    LAB_HEIGHT,
    LAB_SYSTOLIC_BP,
    LAB_WEIGHT,
    OBS_SMOKING_STATUS,
    OPIOID_LADDER,
    PROC_CABG,
    PROC_VITALS,
    SMOKING_STATUS_VALUES,
    UNMAPPED_CONDITION_CODES,
    UNMAPPED_DRUG_CODES,
)
from src.config.settings import settings

DATASET_END = date(2026, 1, 1)

AGE_BANDS = [(0, 17, 0.22), (18, 44, 0.35), (45, 64, 0.26), (65, 84, 0.15), (85, 100, 0.02)]
RACE_WEIGHTS = {"white": 0.60, "black": 0.13, "asian": 0.06, "native": 0.01, "other": 0.20}
ETHNICITY_WEIGHTS = {"nonhispanic": 0.82, "hispanic": 0.18}

FIRST_NAMES_M = [
    "James", "Robert", "John", "Michael", "David", "William", "Richard", "Joseph",
    "Thomas", "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Kevin", "Brian",
]
FIRST_NAMES_F = [
    "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica",
    "Sarah", "Karen", "Nancy", "Lisa", "Betty", "Margaret", "Sandra", "Ashley",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas",
    "Taylor", "Moore", "Jackson", "Martin", "Lee",
]
TOWNS = [
    ("Springfield", "MA", "25013"), ("Worcester", "MA", "25027"), ("Cambridge", "MA", "25017"),
    ("Lowell", "MA", "25017"), ("Brockton", "MA", "25023"), ("Quincy", "MA", "25021"),
]
ORGANIZATIONS = [str(uuid.uuid4()) for _ in range(6)]
PROVIDERS = [str(uuid.uuid4()) for _ in range(25)]
PAYERS = [str(uuid.uuid4()) for _ in range(4)]


def _sample_age(rng: np.random.Generator) -> int:
    lo, hi, _ = AGE_BANDS[rng.choice(len(AGE_BANDS), p=[b[2] for b in AGE_BANDS])]
    return int(rng.integers(lo, hi + 1))


def _sample_weighted(weights: dict, rng: np.random.Generator) -> str:
    keys = list(weights.keys())
    probs = list(weights.values())
    return keys[rng.choice(len(keys), p=probs)]


def generate_patients(n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Generate the patient roster: demographics, mortality, no clinical history yet."""
    rows = []
    for _ in range(n):
        age_years = _sample_age(rng)
        birthdate = DATASET_END - timedelta(days=age_years * 365 + int(rng.integers(0, 365)))
        gender = "M" if rng.random() < 0.5 else "F"
        first = rng.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
        last = rng.choice(LAST_NAMES)
        town, state, county_fips = TOWNS[rng.integers(0, len(TOWNS))]

        death_prob = min(0.40, 0.02 + age_years * 0.0018)
        is_deceased = rng.random() < death_prob and age_years > 1
        deathdate = None
        if is_deceased:
            earliest_death = birthdate + timedelta(days=365)
            deathdate = earliest_death + timedelta(
                days=int(rng.integers(0, max(1, (DATASET_END - earliest_death).days)))
            )

        rows.append({
            "Id": str(uuid.uuid4()),
            "BIRTHDATE": birthdate.isoformat(),
            "DEATHDATE": deathdate.isoformat() if deathdate else None,
            "SSN": f"999-{rng.integers(10, 99)}-{rng.integers(1000, 9999)}",
            "DRIVERS": None,
            "PASSPORT": None,
            "PREFIX": None,
            "FIRST": first,
            "LAST": last,
            "SUFFIX": None,
            "MAIDEN": None,
            "MARITAL": rng.choice(["M", "S"]) if age_years >= 18 else None,
            "RACE": _sample_weighted(RACE_WEIGHTS, rng),
            "ETHNICITY": _sample_weighted(ETHNICITY_WEIGHTS, rng),
            "GENDER": gender,
            "BIRTHPLACE": f"{town}, {state}",
            "ADDRESS": f"{rng.integers(1, 9999)} Main St",
            "CITY": town,
            "STATE": state,
            "COUNTY": county_fips,
            "FIPS": county_fips,
            "ZIP": f"0{rng.integers(1000, 9999)}",
            "LAT": round(42.0 + rng.random(), 6),
            "LON": round(-72.5 + rng.random(), 6),
            "HEALTHCARE_EXPENSES": round(float(rng.uniform(2000, 250000)), 2),
            "HEALTHCARE_COVERAGE": round(float(rng.uniform(0, 50000)), 2),
            "INCOME": int(rng.uniform(15000, 180000)),
            "_age_years": age_years,
        })
    return pd.DataFrame(rows)


class PatientTimeline:
    """Accumulates one patient's encounters/conditions/medications/observations/
    procedures. Each `visit(...)` call creates one encounter and returns its id
    and date, so the event that triggered the visit (a diagnosis, a
    prescription, a lab panel) can attach itself to it — an encounter without a
    reason to exist doesn't get generated here."""

    def __init__(self, patient_id: str, birthdate: date, deathdate: date | None, rng):
        self.patient_id = patient_id
        self.birthdate = birthdate
        self.deathdate = deathdate
        self.rng = rng
        self.encounters: list[dict] = []
        self.conditions: list[dict] = []
        self.medications: list[dict] = []
        self.observations: list[dict] = []
        self.procedures: list[dict] = []

    @property
    def last_possible_date(self) -> date:
        return self.deathdate or DATASET_END

    def visit(self, when: date, encounter_class: str, reason_code: str = "", reason_desc: str = "") -> str:
        when = min(max(when, self.birthdate), self.last_possible_date)
        encounter_id = str(uuid.uuid4())
        cost = round(float(self.rng.uniform(75, 1500)), 2)
        self.encounters.append({
            "Id": encounter_id,
            "START": when.isoformat(),
            "STOP": when.isoformat(),
            "PATIENT": self.patient_id,
            "ORGANIZATION": self.rng.choice(ORGANIZATIONS),
            "PROVIDER": self.rng.choice(PROVIDERS),
            "PAYER": self.rng.choice(PAYERS),
            "ENCOUNTERCLASS": encounter_class,
            "CODE": "185349003",
            "DESCRIPTION": "Encounter for check up",
            "BASE_ENCOUNTER_COST": cost,
            "TOTAL_CLAIM_COST": round(cost * float(self.rng.uniform(1.0, 3.0)), 2),
            "PAYER_COVERAGE": round(cost * float(self.rng.uniform(0.4, 0.9)), 2),
            "REASONCODE": reason_code or None,
            "REASONDESCRIPTION": reason_desc or None,
        })
        return encounter_id

    def add_condition(self, encounter_id: str, start: date, code, stop: date | None = None):
        self.conditions.append({
            "START": start.isoformat(), "STOP": stop.isoformat() if stop else None,
            "PATIENT": self.patient_id, "ENCOUNTER": encounter_id,
            "CODE": code.code if hasattr(code, "code") else code[0],
            "DESCRIPTION": code.concept_name if hasattr(code, "concept_name") else code[1],
        })

    def add_medication(self, encounter_id: str, start: date, code, stop: date | None, dispenses: int = 1):
        cost = round(float(self.rng.uniform(10, 400)), 2)
        self.medications.append({
            "START": start.isoformat(), "STOP": stop.isoformat() if stop else None,
            "PATIENT": self.patient_id, "PAYER": self.rng.choice(PAYERS),
            "ENCOUNTER": encounter_id,
            "CODE": code.code if hasattr(code, "code") else code[0],
            "DESCRIPTION": code.concept_name if hasattr(code, "concept_name") else code[1],
            "BASE_COST": cost, "PAYER_COVERAGE": round(cost * 0.7, 2),
            "DISPENSES": dispenses, "TOTALCOST": round(cost * dispenses, 2),
            "REASONCODE": None, "REASONDESCRIPTION": None,
        })

    def add_observation(self, encounter_id: str, when: date, code, value, units: str, category: str, obs_type: str):
        self.observations.append({
            "DATE": when.isoformat(), "PATIENT": self.patient_id, "ENCOUNTER": encounter_id,
            "CATEGORY": category,
            "CODE": code.code, "DESCRIPTION": code.concept_name,
            "VALUE": value, "UNITS": units, "TYPE": obs_type,
        })

    def add_procedure(self, encounter_id: str, when: date, code):
        cost = round(float(self.rng.uniform(200, 15000)), 2)
        self.procedures.append({
            "START": when.isoformat(), "STOP": when.isoformat(),
            "PATIENT": self.patient_id, "ENCOUNTER": encounter_id,
            "CODE": code.code, "DESCRIPTION": code.concept_name,
            "BASE_COST": cost, "REASONCODE": None, "REASONDESCRIPTION": None,
        })


def _record_vitals(tl: PatientTimeline, encounter_id: str, when: date, rng, hypertensive: bool, diabetic: bool):
    systolic = rng.normal(148 if hypertensive else 118, 10)
    diastolic = rng.normal(92 if hypertensive else 76, 7)
    tl.add_observation(encounter_id, when, LAB_SYSTOLIC_BP, round(float(systolic), 1), "mmHg", "vital-signs", "numeric")
    tl.add_observation(encounter_id, when, LAB_DIASTOLIC_BP, round(float(diastolic), 1), "mmHg", "vital-signs", "numeric")
    tl.add_observation(encounter_id, when, LAB_HEART_RATE, round(float(rng.normal(74, 10)), 1), "bpm", "vital-signs", "numeric")
    height_cm = round(float(rng.normal(168, 10)), 1)
    weight_kg = round(float(rng.normal(82 if diabetic else 74, 14)), 1)
    tl.add_observation(encounter_id, when, LAB_HEIGHT, height_cm, "cm", "vital-signs", "numeric")
    tl.add_observation(encounter_id, when, LAB_WEIGHT, weight_kg, "kg", "vital-signs", "numeric")
    bmi = round(weight_kg / ((height_cm / 100) ** 2), 1)
    tl.add_observation(encounter_id, when, LAB_BMI, bmi, "kg/m2", "vital-signs", "numeric")
    tl.add_procedure(encounter_id, when, PROC_VITALS)


def _generate_patient_events(patient_row: pd.Series, rng: np.random.Generator) -> PatientTimeline:
    birthdate = date.fromisoformat(patient_row["BIRTHDATE"])
    deathdate = date.fromisoformat(patient_row["DEATHDATE"]) if patient_row["DEATHDATE"] else None
    age_years = patient_row["_age_years"]
    tl = PatientTimeline(patient_row["Id"], birthdate, deathdate, rng)

    adult = age_years >= 18
    if not adult:
        return tl

    # Chronic condition assignment — probabilities scale with age, which is
    # what makes the cohorts observable in aggregate rather than uniformly
    # spread across the population.
    p_t2dm = min(0.45, 0.03 + max(0, age_years - 30) * 0.008)
    p_htn = min(0.65, 0.05 + max(0, age_years - 25) * 0.012)
    p_lipid = min(0.55, 0.05 + max(0, age_years - 25) * 0.010)
    p_asthma = 0.06
    p_smoker = 0.15

    has_t2dm = rng.random() < p_t2dm
    has_htn = rng.random() < p_htn
    has_lipid = rng.random() < p_lipid
    has_asthma = rng.random() < p_asthma
    is_smoker = rng.random() < p_smoker

    # Elderly patients get pushed toward comorbidity so polypharmacy_elderly
    # has real members: five or more concurrently active prescriptions.
    if age_years >= 65:
        has_htn = has_htn or rng.random() < 0.5
        has_lipid = has_lipid or rng.random() < 0.4

    adult_start = birthdate + timedelta(days=18 * 365)
    last_date = tl.last_possible_date
    if adult_start >= last_date:
        return tl

    # Annual wellness visits.
    when = adult_start + timedelta(days=int(rng.integers(0, 365)))
    while when < last_date:
        enc = tl.visit(when, "wellness")
        _record_vitals(tl, enc, when, rng, hypertensive=has_htn, diabetic=has_t2dm)
        if rng.random() < 0.3:
            status = SMOKING_STATUS_VALUES[2] if is_smoker else SMOKING_STATUS_VALUES[0]
            tl.add_observation(enc, when, OBS_SMOKING_STATUS, status, "", "social-history", "text")
        when += timedelta(days=int(rng.integers(300, 420)))

    active_drugs: list[tuple] = []  # (code, start_date) still open at generation time

    def start_drug(code, when: date):
        # Every call site here is a maintenance medication (metformin, an
        # antihypertensive, a statin, the polypharmacy padding drugs) —
        # clinically, those stay active until something stops them, not for
        # a random few months. DISPENSES scales with how long the
        # prescription has actually been running, so the exposure duration
        # transform_drug_exposure derives from it (dispenses * 30 days)
        # lands close to last_date instead of understating a years-long
        # prescription as a single short fill — which is also what makes
        # polypharmacy_elderly (5+ concurrently active drugs) findable at
        # all downstream.
        # No cap here on purpose: a prescription started decades before
        # last_date needs a dispenses count that actually reaches last_date,
        # not one truncated to an arbitrary ceiling partway through — a
        # 30-year metformin prescription is unusual but not implausible.
        dispenses = max(1, (last_date - when).days // 30)
        enc = tl.visit(when, "ambulatory")
        tl.add_medication(enc, when, code, None, dispenses)
        active_drugs.append((code, when))
        return enc

    diagnosis_date = None
    if has_t2dm:
        onset_age = min(age_years, max(35, int(rng.integers(35, 76))))
        diagnosis_date = birthdate + timedelta(days=onset_age * 365 + int(rng.integers(0, 365)))
        diagnosis_date = max(diagnosis_date, adult_start)
        if diagnosis_date < last_date:
            enc = tl.visit(diagnosis_date, "ambulatory")
            source = CONDITION_DIABETES_LEGACY if rng.random() < 0.15 else CONDITION_T2DM
            tl.add_condition(enc, diagnosis_date, source)
            drug_code = DRUG_METFORMIN_BRAND if rng.random() < 0.1 else DRUG_METFORMIN
            start_drug(drug_code, diagnosis_date + timedelta(days=int(rng.integers(0, 14))))

            for follow_up_code, prob in [
                (LAB_HBA1C, 0.9), (LAB_GLUCOSE, 0.9),
            ]:
                fu = diagnosis_date + timedelta(days=int(rng.integers(60, 180)))
                if fu < last_date and rng.random() < prob:
                    fu_enc = tl.visit(fu, "ambulatory")
                    if follow_up_code is LAB_HBA1C:
                        value = round(float(rng.normal(7.8, 1.2)), 1)
                    else:
                        value = round(float(rng.normal(165, 30)), 1)
                    unit = "%" if follow_up_code is LAB_HBA1C else "mg/dL"
                    tl.add_observation(fu_enc, fu, follow_up_code, value, unit, "laboratory", "numeric")

            # Diabetes complications cohort: cardiovascular event within a year
            # of diagnosis for a meaningful minority.
            if rng.random() < 0.18:
                event_code = rng.choice([CONDITION_MI, CONDITION_STROKE, CONDITION_HEART_FAILURE, CONDITION_CAD])
                event_date = diagnosis_date + timedelta(days=int(rng.integers(10, 360)))
                if event_date < last_date:
                    ev_enc = tl.visit(event_date, "emergency", event_code.code, event_code.concept_name)
                    tl.add_condition(ev_enc, event_date, event_code)
            # Longer-horizon microvascular complications.
            if rng.random() < 0.12:
                comp_code = rng.choice([CONDITION_DIABETIC_NEPHROPATHY, CONDITION_DIABETIC_RETINOPATHY, CONDITION_CKD])
                comp_date = diagnosis_date + timedelta(days=int(rng.integers(365, 365 * 6)))
                if comp_date < last_date:
                    comp_enc = tl.visit(comp_date, "ambulatory")
                    tl.add_condition(comp_enc, comp_date, comp_code)

    if has_htn:
        onset = max(adult_start, birthdate + timedelta(days=max(25, age_years - 5) * 365))
        if onset < last_date:
            enc = tl.visit(onset, "ambulatory")
            tl.add_condition(enc, onset, CONDITION_HYPERTENSION)
            start_drug(rng.choice([DRUG_LISINOPRIL, DRUG_AMLODIPINE]), onset + timedelta(days=int(rng.integers(0, 21))))
            if age_years >= 65 and rng.random() < 0.5:
                start_drug(DRUG_HCTZ, onset + timedelta(days=int(rng.integers(30, 120))))

    if has_lipid:
        onset = max(adult_start, birthdate + timedelta(days=max(28, age_years - 3) * 365))
        if onset < last_date:
            enc = tl.visit(onset, "ambulatory")
            tl.add_condition(enc, onset, CONDITION_HYPERLIPIDEMIA)
            start_drug(rng.choice([DRUG_ATORVASTATIN, DRUG_LEVOTHYROXINE]), onset + timedelta(days=int(rng.integers(0, 21))))

    if has_asthma:
        onset = birthdate + timedelta(days=int(rng.integers(2, min(age_years, 40) + 1)) * 365)
        if adult_start <= onset < last_date:
            enc = tl.visit(onset, "ambulatory")
            tl.add_condition(enc, onset, CONDITION_ASTHMA if rng.random() < 0.7 else CONDITION_COPD)
            start_drug(DRUG_ALBUTEROL, onset + timedelta(days=int(rng.integers(0, 14))))

    # Extra polypharmacy padding for elderly patients so 5+ concurrent active
    # prescriptions is a routine outcome of this branch, not a rare fluke.
    if age_years >= 65 and rng.random() < 0.6:
        pad_start = last_date - timedelta(days=int(rng.integers(180, 700)))
        pad_start = max(pad_start, adult_start)
        if pad_start < last_date:
            for pad_code in rng.choice([DRUG_ASPIRIN, DRUG_OMEPRAZOLE, DRUG_LEVOTHYROXINE], size=2, replace=False):
                start_drug(pad_code, pad_start + timedelta(days=int(rng.integers(0, 60))))

    # Opioid escalation cohort — a real fraction of patients with a
    # cardiovascular procedure, plus a small flat background rate elsewhere.
    had_cabg = rng.random() < 0.04 and has_t2dm
    escalate = had_cabg or rng.random() < 0.03
    if escalate and adult_start < last_date:
        if had_cabg:
            cabg_date = adult_start + timedelta(days=int(rng.integers(0, max(1, (last_date - adult_start).days))))
            enc = tl.visit(cabg_date, "inpatient", PROC_CABG.code, PROC_CABG.concept_name)
            tl.add_procedure(enc, cabg_date, PROC_CABG)
            ladder_start = cabg_date
        else:
            ladder_start = adult_start + timedelta(days=int(rng.integers(0, max(1, (last_date - adult_start).days))))

        step_date = ladder_start
        for step_code in OPIOID_LADDER:
            if step_date >= last_date:
                break
            enc = tl.visit(step_date, "ambulatory")
            end = min(step_date + timedelta(days=45), last_date)
            tl.add_medication(enc, step_date, step_code, end, dispenses=1)
            step_date += timedelta(days=int(rng.integers(30, 60)))

    # Background noise: minor self-limiting illness, occasionally.
    for _ in range(int(rng.integers(0, 3))):
        when = adult_start + timedelta(days=int(rng.integers(0, max(1, (last_date - adult_start).days))))
        enc = tl.visit(when, "urgentcare")
        tl.add_condition(enc, when, CONDITION_PHARYNGITIS, stop=when + timedelta(days=7))

    # Deliberate vocabulary gaps: a small fraction of patients present with a
    # condition or drug this project's demo vocabulary doesn't cover, so
    # mapping-coverage and DQD conformance numbers reflect a real gap instead
    # of a trivial 100%.
    if rng.random() < 0.04:
        code, desc = UNMAPPED_CONDITION_CODES[rng.integers(0, len(UNMAPPED_CONDITION_CODES))]
        when = adult_start + timedelta(days=int(rng.integers(0, max(1, (last_date - adult_start).days))))
        enc = tl.visit(when, "ambulatory")
        tl.add_condition(enc, when, (code, desc))
    if rng.random() < 0.03:
        code, desc = UNMAPPED_DRUG_CODES[rng.integers(0, len(UNMAPPED_DRUG_CODES))]
        when = adult_start + timedelta(days=int(rng.integers(0, max(1, (last_date - adult_start).days))))
        start_drug((code, desc), when)

    return tl


@click.command()
@click.option(
    "--population", type=int, default=None,
    help="Number of patients to generate. Defaults to settings.synthea_population.",
)
@click.option("--seed", type=int, default=42, help="Random seed, for reproducible output.")
@click.option("--output-dir", type=click.Path(path_type=Path), default=None, help="Defaults to settings.synthea_output_dir.")
def main(population: int | None, seed: int, output_dir: Path | None):
    """Generate a synthetic Synthea-format population and write it to CSV."""
    n = population or settings.synthea_population
    out = output_dir or settings.synthea_output_dir
    out.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)
    logger.info(f"Generating {n:,} synthetic patients (seed={seed})")

    patients = generate_patients(n, rng)

    encounters, conditions, medications, observations, procedures = [], [], [], [], []
    for _, row in patients.iterrows():
        tl = _generate_patient_events(row, rng)
        encounters.extend(tl.encounters)
        conditions.extend(tl.conditions)
        medications.extend(tl.medications)
        observations.extend(tl.observations)
        procedures.extend(tl.procedures)

    tables = {
        "patients": patients.drop(columns=["_age_years"]),
        "encounters": pd.DataFrame(encounters),
        "conditions": pd.DataFrame(conditions),
        "medications": pd.DataFrame(medications),
        "observations": pd.DataFrame(observations),
        "procedures": pd.DataFrame(procedures),
    }

    for name, df in tables.items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info(f"  {name}.csv: {len(df):,} rows")

    logger.info(f"Demo population written to {out}")


if __name__ == "__main__":
    main()
