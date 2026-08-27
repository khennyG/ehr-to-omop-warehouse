"""Shared clinical code catalog for the demo data generator and demo vocabulary
builder.

Both scripts.generate_demo_data and scripts.build_demo_vocabulary import from
here so the synthetic patient records and the vocabulary they map against never
drift apart — every code the generator writes into a patient's chart has a
matching row in the demo CONCEPT.csv, with two deliberate exceptions (see
UNMAPPED_CONDITION_CODES / UNMAPPED_DRUG_CODES below) that exist specifically so
the pipeline's quality checks have a real gap to report instead of a trivial
100% pass rate.

The source codes here — the SNOMED CT, RxNorm, and LOINC values — are real,
established codes for common conditions, drugs, and labs. The concept_id values
assigned to them are not: matching a source code to its true Athena-assigned
concept_id requires the actual Athena export, which needs a licensed OHDSI
account this project doesn't have. Rather than guess at numbers and risk
passing off a guess as fact, every concept_id here is assigned locally, in the
range OMOP itself reserves for exactly this situation — concept_id >=
2,000,000,000 is the standing OMOP convention for concepts that aren't from an
Athena vocabulary release. scripts/download_vocabularies.py documents how to
swap in the real thing for production use.
"""

from dataclasses import dataclass, field

_next_concept_id = iter(range(2_000_000_001, 2_000_999_999))


@dataclass(frozen=True)
class ClinicalCode:
    code: str
    vocabulary_id: str
    concept_name: str
    domain_id: str
    concept_class_id: str
    concept_id: int = field(default_factory=lambda: next(_next_concept_id))
    standard: bool = True
    maps_to: "ClinicalCode | None" = None  # set for non-standard source codes


# ── Conditions (SNOMED CT) ───────────────────────────────────────────────────
# Weighted toward the three cohorts this project analyzes: diabetes and its
# cardiovascular/renal/ocular complications, hypertension and hyperlipidemia as
# the polypharmacy backbone, and a few common, low-acuity conditions so the
# population isn't unrealistically sick.

CONDITION_T2DM = ClinicalCode("44054006", "SNOMED", "Type 2 diabetes mellitus", "Condition", "Clinical Finding")
CONDITION_HYPERTENSION = ClinicalCode("38341003", "SNOMED", "Hypertensive disorder", "Condition", "Clinical Finding")
CONDITION_HYPERLIPIDEMIA = ClinicalCode("55822004", "SNOMED", "Hyperlipidemia", "Condition", "Clinical Finding")
CONDITION_CAD = ClinicalCode("53741008", "SNOMED", "Coronary arteriosclerosis", "Condition", "Clinical Finding")
CONDITION_MI = ClinicalCode("22298006", "SNOMED", "Myocardial infarction", "Condition", "Clinical Finding")
CONDITION_HEART_FAILURE = ClinicalCode("84114007", "SNOMED", "Heart failure", "Condition", "Clinical Finding")
CONDITION_STROKE = ClinicalCode("230690007", "SNOMED", "Cerebrovascular accident", "Condition", "Clinical Finding")
CONDITION_DIABETIC_NEPHROPATHY = ClinicalCode("236425005", "SNOMED", "Diabetic nephropathy", "Condition", "Clinical Finding")
CONDITION_DIABETIC_RETINOPATHY = ClinicalCode("4855003", "SNOMED", "Diabetic retinopathy", "Condition", "Clinical Finding")
CONDITION_CKD = ClinicalCode("431855005", "SNOMED", "Chronic kidney disease stage 3", "Condition", "Clinical Finding")
CONDITION_ASTHMA = ClinicalCode("195967001", "SNOMED", "Asthma", "Condition", "Clinical Finding")
CONDITION_COPD = ClinicalCode("13645005", "SNOMED", "Chronic obstructive pulmonary disease", "Condition", "Clinical Finding")
CONDITION_ANEMIA = ClinicalCode("271737000", "SNOMED", "Anemia", "Condition", "Clinical Finding")
CONDITION_PHARYNGITIS = ClinicalCode("195662009", "SNOMED", "Acute viral pharyngitis", "Condition", "Clinical Finding")

# A non-standard, older classification of diabetes that a real vocabulary maps
# onto the current standard concept — this is what exercises the "Maps to" hop
# in VocabularyMapper.to_standard() rather than every code already being
# standard on arrival (which real OMOP vocabularies never are, uniformly).
CONDITION_DIABETES_LEGACY = ClinicalCode(
    "73211009", "SNOMED", "Diabetes mellitus", "Condition", "Clinical Finding",
    standard=False, maps_to=CONDITION_T2DM,
)

STANDARD_CONDITIONS = [
    CONDITION_T2DM, CONDITION_HYPERTENSION, CONDITION_HYPERLIPIDEMIA, CONDITION_CAD,
    CONDITION_MI, CONDITION_HEART_FAILURE, CONDITION_STROKE, CONDITION_DIABETIC_NEPHROPATHY,
    CONDITION_DIABETIC_RETINOPATHY, CONDITION_CKD, CONDITION_ASTHMA, CONDITION_COPD,
    CONDITION_ANEMIA, CONDITION_PHARYNGITIS,
]
NONSTANDARD_CONDITIONS = [CONDITION_DIABETES_LEGACY]

# Condition codes the generator uses but the vocabulary deliberately omits —
# every real-world vocabulary has a long tail it hasn't caught up to yet, and
# a demo pipeline that maps 100% of everything doesn't demonstrate that DQD's
# conformance checks or the mapping-coverage report actually do anything.
UNMAPPED_CONDITION_CODES = [
    ("47693006", "Uncombable hair syndrome"),  # deliberately obscure/rare
    ("724746003", "Idiopathic pulmonary fibrosis"),
]

# ── Drugs (RxNorm ingredients) ───────────────────────────────────────────────
# Opioids are listed in ascending potency (approximate morphine-milligram-
# equivalent ordering) on purpose — the opioid_escalation cohort is defined by
# a patient's prescriptions moving up this list over time.

DRUG_METFORMIN = ClinicalCode("6809", "RxNorm", "Metformin", "Drug", "Ingredient")
DRUG_LISINOPRIL = ClinicalCode("29046", "RxNorm", "Lisinopril", "Drug", "Ingredient")
DRUG_ATORVASTATIN = ClinicalCode("83367", "RxNorm", "Atorvastatin", "Drug", "Ingredient")
DRUG_SIMVASTATIN = ClinicalCode("36567", "RxNorm", "Simvastatin", "Drug", "Ingredient")
DRUG_AMLODIPINE = ClinicalCode("17767", "RxNorm", "Amlodipine", "Drug", "Ingredient")
DRUG_METOPROLOL = ClinicalCode("6918", "RxNorm", "Metoprolol", "Drug", "Ingredient")
DRUG_HCTZ = ClinicalCode("5487", "RxNorm", "Hydrochlorothiazide", "Drug", "Ingredient")
DRUG_FUROSEMIDE = ClinicalCode("4603", "RxNorm", "Furosemide", "Drug", "Ingredient")
DRUG_ASPIRIN = ClinicalCode("1191", "RxNorm", "Aspirin", "Drug", "Ingredient")
DRUG_WARFARIN = ClinicalCode("11289", "RxNorm", "Warfarin", "Drug", "Ingredient")
DRUG_LEVOTHYROXINE = ClinicalCode("10582", "RxNorm", "Levothyroxine", "Drug", "Ingredient")
DRUG_OMEPRAZOLE = ClinicalCode("7646", "RxNorm", "Omeprazole", "Drug", "Ingredient")
DRUG_ALBUTEROL = ClinicalCode("435", "RxNorm", "Albuterol", "Drug", "Ingredient")
DRUG_INSULIN = ClinicalCode("5856", "RxNorm", "Insulin", "Drug", "Ingredient")
DRUG_ACETAMINOPHEN = ClinicalCode("161", "RxNorm", "Acetaminophen", "Drug", "Ingredient")

# Opioid escalation ladder, weakest to strongest.
DRUG_CODEINE = ClinicalCode("2670", "RxNorm", "Codeine", "Drug", "Ingredient")
DRUG_HYDROCODONE = ClinicalCode("5489", "RxNorm", "Hydrocodone", "Drug", "Ingredient")
DRUG_OXYCODONE = ClinicalCode("7804", "RxNorm", "Oxycodone", "Drug", "Ingredient")
DRUG_FENTANYL = ClinicalCode("4337", "RxNorm", "Fentanyl", "Drug", "Ingredient")
OPIOID_LADDER = [DRUG_CODEINE, DRUG_HYDROCODONE, DRUG_OXYCODONE, DRUG_FENTANYL]

# A branded product code that maps onto the metformin ingredient — the drug-side
# counterpart to CONDITION_DIABETES_LEGACY, same reasoning.
DRUG_METFORMIN_BRAND = ClinicalCode(
    "861007", "RxNorm", "Metformin hydrochloride 500 MG Oral Tablet", "Drug", "Clinical Drug",
    standard=False, maps_to=DRUG_METFORMIN,
)

STANDARD_DRUGS = [
    DRUG_METFORMIN, DRUG_LISINOPRIL, DRUG_ATORVASTATIN, DRUG_SIMVASTATIN, DRUG_AMLODIPINE,
    DRUG_METOPROLOL, DRUG_HCTZ, DRUG_FUROSEMIDE, DRUG_ASPIRIN, DRUG_WARFARIN,
    DRUG_LEVOTHYROXINE, DRUG_OMEPRAZOLE, DRUG_ALBUTEROL, DRUG_INSULIN, DRUG_ACETAMINOPHEN,
    *OPIOID_LADDER,
]
NONSTANDARD_DRUGS = [DRUG_METFORMIN_BRAND]

UNMAPPED_DRUG_CODES = [
    ("1946825", "Elexacaftor / tezacaftor / ivacaftor"),  # narrow-indication specialty drug
]

# ── Labs and vitals (LOINC) ──────────────────────────────────────────────────

LAB_HBA1C = ClinicalCode("4548-4", "LOINC", "Hemoglobin A1c", "Measurement", "Lab Test")
LAB_GLUCOSE = ClinicalCode("2345-7", "LOINC", "Glucose", "Measurement", "Lab Test")
LAB_SYSTOLIC_BP = ClinicalCode("8480-6", "LOINC", "Systolic blood pressure", "Measurement", "Clinical Observation")
LAB_DIASTOLIC_BP = ClinicalCode("8462-4", "LOINC", "Diastolic blood pressure", "Measurement", "Clinical Observation")
LAB_TOTAL_CHOLESTEROL = ClinicalCode("2093-3", "LOINC", "Total cholesterol", "Measurement", "Lab Test")
LAB_HDL = ClinicalCode("2085-9", "LOINC", "HDL cholesterol", "Measurement", "Lab Test")
LAB_LDL = ClinicalCode("18262-6", "LOINC", "LDL cholesterol", "Measurement", "Lab Test")
LAB_WEIGHT = ClinicalCode("3141-9", "LOINC", "Body weight", "Measurement", "Clinical Observation")
LAB_HEIGHT = ClinicalCode("8302-2", "LOINC", "Body height", "Measurement", "Clinical Observation")
LAB_BMI = ClinicalCode("39156-5", "LOINC", "Body mass index", "Measurement", "Clinical Observation")
LAB_CREATININE = ClinicalCode("2160-0", "LOINC", "Creatinine", "Measurement", "Lab Test")
LAB_BUN = ClinicalCode("6299-2", "LOINC", "Urea nitrogen", "Measurement", "Lab Test")
LAB_HEMOGLOBIN = ClinicalCode("718-7", "LOINC", "Hemoglobin", "Measurement", "Lab Test")
LAB_WBC = ClinicalCode("6690-2", "LOINC", "Leukocytes", "Measurement", "Lab Test")
LAB_PLATELETS = ClinicalCode("777-3", "LOINC", "Platelets", "Measurement", "Lab Test")
LAB_HEART_RATE = ClinicalCode("8867-4", "LOINC", "Heart rate", "Measurement", "Clinical Observation")

STANDARD_LABS = [
    LAB_HBA1C, LAB_GLUCOSE, LAB_SYSTOLIC_BP, LAB_DIASTOLIC_BP, LAB_TOTAL_CHOLESTEROL,
    LAB_HDL, LAB_LDL, LAB_WEIGHT, LAB_HEIGHT, LAB_BMI, LAB_CREATININE, LAB_BUN,
    LAB_HEMOGLOBIN, LAB_WBC, LAB_PLATELETS, LAB_HEART_RATE,
]

# ── Text-valued observations (LOINC) ─────────────────────────────────────────

OBS_SMOKING_STATUS = ClinicalCode("72166-2", "LOINC", "Tobacco smoking status", "Observation", "Clinical Observation")
SMOKING_STATUS_VALUES = [
    "Never smoker", "Former smoker", "Current every day smoker", "Current some day smoker",
]

STANDARD_OBSERVATIONS = [OBS_SMOKING_STATUS]

# ── Procedures (SNOMED CT) ───────────────────────────────────────────────────

PROC_VITALS = ClinicalCode("46680005", "SNOMED", "Vital signs measurement", "Procedure", "Procedure")
PROC_PHYSICAL_EXAM = ClinicalCode("271442007", "SNOMED", "Physical examination procedure", "Procedure", "Procedure")
PROC_HEMODIALYSIS = ClinicalCode("385763009", "SNOMED", "Hemodialysis", "Procedure", "Procedure")
PROC_CABG = ClinicalCode("232717009", "SNOMED", "Coronary artery bypass grafting", "Procedure", "Procedure")

STANDARD_PROCEDURES = [PROC_VITALS, PROC_PHYSICAL_EXAM, PROC_HEMODIALYSIS, PROC_CABG]

ALL_STANDARD_CODES = (
    STANDARD_CONDITIONS + STANDARD_DRUGS + STANDARD_LABS
    + STANDARD_OBSERVATIONS + STANDARD_PROCEDURES
)
ALL_NONSTANDARD_CODES = NONSTANDARD_CONDITIONS + NONSTANDARD_DRUGS

# ── Administrative concepts ──────────────────────────────────────────────────
# These are real Athena-assigned concept_ids, not locally assigned ones — unlike
# the clinical codes above, they're hardcoded directly into
# src/transform/omop_transformer.py rather than resolved through
# VocabularyMapper, so the demo vocabulary has to seed these exact values for
# the foreign keys on person.gender_concept_id, visit_occurrence.visit_concept_id,
# and so on to resolve at all.
GENDER_CONCEPTS = [(8507, "Male"), (8532, "Female")]
RACE_CONCEPTS = [
    (8527, "White"), (8516, "Black or African American"), (8515, "Asian"),
    (8657, "American Indian or Alaska Native"), (8522, "Other Race"),
]
ETHNICITY_CONCEPTS = [(38003563, "Hispanic or Latino"), (38003564, "Not Hispanic or Latino")]
VISIT_CONCEPTS = [(9202, "Outpatient Visit"), (9201, "Inpatient Visit"), (9203, "Emergency Room Visit")]
TYPE_CONCEPTS = [
    (32817, "EHR"), (32810, "Claim"), (32838, "Prescription written"),
    (44814724, "Period covering healthcare encounters"),
]
NO_MATCHING_CONCEPT = (0, "No matching concept")
