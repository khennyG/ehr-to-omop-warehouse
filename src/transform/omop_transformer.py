"""Transform Synthea staging tables into OMOP CDM v5.4 clinical data tables.

This is the core of the pipeline. Each function takes a staging DataFrame
(loaded by the extract module) and produces one or more OMOP tables:

  Synthea patients     -> OMOP person, observation_period, death
  Synthea encounters   -> OMOP visit_occurrence
  Synthea conditions   -> OMOP condition_occurrence
  Synthea medications  -> OMOP drug_exposure
  Synthea observations -> OMOP measurement, observation
  Synthea procedures   -> OMOP procedure_occurrence

Each transformation:
  1. Maps source codes to standard concept_ids via VocabularyMapper
  2. Generates OMOP-required surrogate keys (person_id, visit_occurrence_id, etc.)
  3. Computes derived fields (observation periods, type concepts)
  4. Handles missing/null values according to OMOP conventions (0 for unknown concepts)
"""


import pandas as pd
from loguru import logger

from src.transform.vocabulary_mapper import VocabularyMapper

# OMOP type concepts — these indicate the provenance of the record
TYPE_CONCEPT = {
    "ehr": 32817,         # EHR
    "claim": 32810,       # Claim
    "prescription": 32838, # Prescription written
}


def _generate_ids(df: pd.DataFrame, id_column: str) -> pd.DataFrame:
    """Add a sequential integer ID column, starting at 1.

    Every caller here has just filtered out some rows (unmapped persons, a
    non-numeric value, whatever), so the incoming index is whatever survived
    that filter — not 0..n-1. Resetting it before assigning IDs is what keeps
    positional access (.loc[0], .iloc[0]) on the result meaning what it looks
    like it means, instead of silently depending on which rows a filter
    upstream happened to drop.
    """
    df = df.reset_index(drop=True).copy()
    df[id_column] = range(1, len(df) + 1)
    return df


def transform_person(stg_patients: pd.DataFrame, mapper: VocabularyMapper) -> pd.DataFrame:
    """Synthea patients -> OMOP person table.

    Maps gender and race to OMOP standard concepts. Splits birth date into
    year/month/day components as OMOP requires.
    """
    logger.info(f"Transforming {len(stg_patients):,} patients to OMOP person")

    gender_map = {"M": 8507, "F": 8532}  # OMOP gender concept_ids
    race_map = {
        "white": 8527,
        "black": 8516,
        "asian": 8515,
        "native": 8657,
        "other": 8522,
    }
    ethnicity_map = {
        "hispanic": 38003563,
        "nonhispanic": 38003564,
    }

    person = pd.DataFrame({
        "person_source_value": stg_patients["Id"],
        "gender_concept_id": stg_patients["GENDER"].map(gender_map).fillna(0).astype(int),
        "year_of_birth": pd.to_datetime(stg_patients["BIRTHDATE"]).dt.year,
        "month_of_birth": pd.to_datetime(stg_patients["BIRTHDATE"]).dt.month,
        "day_of_birth": pd.to_datetime(stg_patients["BIRTHDATE"]).dt.day,
        "birth_datetime": pd.to_datetime(stg_patients["BIRTHDATE"]),
        "race_concept_id": stg_patients["RACE"].str.lower().map(race_map).fillna(0).astype(int),
        "ethnicity_concept_id": stg_patients["ETHNICITY"].str.lower().map(ethnicity_map).fillna(0).astype(int),
        "gender_source_value": stg_patients["GENDER"],
        "race_source_value": stg_patients["RACE"],
        "ethnicity_source_value": stg_patients["ETHNICITY"],
    })

    person = _generate_ids(person, "person_id")
    logger.info(f"  Produced {len(person):,} person records")
    return person


def transform_visit_occurrence(
    stg_encounters: pd.DataFrame,
    person_lookup: dict[str, int],
    mapper: VocabularyMapper,
) -> pd.DataFrame:
    """Synthea encounters -> OMOP visit_occurrence.

    Maps encounter class (ambulatory, inpatient, emergency, etc.) to OMOP
    visit concepts.
    """
    logger.info(f"Transforming {len(stg_encounters):,} encounters to visit_occurrence")

    visit_concept_map = {
        "ambulatory": 9202,    # Outpatient Visit
        "outpatient": 9202,
        "inpatient": 9201,     # Inpatient Visit
        "emergency": 9203,     # Emergency Room Visit
        "urgentcare": 9203,
        "wellness": 9202,
    }

    visits = pd.DataFrame({
        "person_id": stg_encounters["PATIENT"].map(person_lookup).fillna(0).astype(int),
        "visit_concept_id": stg_encounters["ENCOUNTERCLASS"].str.lower().map(visit_concept_map).fillna(0).astype(int),
        "visit_start_date": pd.to_datetime(stg_encounters["START"]).dt.date,
        "visit_start_datetime": pd.to_datetime(stg_encounters["START"]),
        "visit_end_date": pd.to_datetime(stg_encounters["STOP"]).dt.date,
        "visit_end_datetime": pd.to_datetime(stg_encounters["STOP"]),
        "visit_type_concept_id": TYPE_CONCEPT["ehr"],
        "visit_source_value": stg_encounters["ENCOUNTERCLASS"],
        "encounter_source_value": stg_encounters["Id"],
    })

    # Filter out rows where person_id mapping failed
    unmapped = (visits["person_id"] == 0).sum()
    if unmapped > 0:
        logger.warning(f"  {unmapped} encounters with unmapped patient IDs")
    visits = visits[visits["person_id"] != 0]

    visits = _generate_ids(visits, "visit_occurrence_id")
    logger.info(f"  Produced {len(visits):,} visit_occurrence records")
    return visits


def transform_condition_occurrence(
    stg_conditions: pd.DataFrame,
    person_lookup: dict[str, int],
    visit_lookup: dict[str, int],
    mapper: VocabularyMapper,
) -> pd.DataFrame:
    """Synthea conditions -> OMOP condition_occurrence.

    Resolves SNOMED CT codes to standard concept_ids via the vocabulary mapper.
    """
    logger.info(f"Transforming {len(stg_conditions):,} conditions to condition_occurrence")

    # Map SNOMED codes to standard concepts
    concept_ids = []
    source_concept_ids = []
    for code in stg_conditions["CODE"].astype(str):
        source_id, standard_id = mapper.resolve(code, "SNOMED")
        source_concept_ids.append(source_id)
        concept_ids.append(standard_id)

    conditions = pd.DataFrame({
        "person_id": stg_conditions["PATIENT"].map(person_lookup).fillna(0).astype(int),
        "condition_concept_id": concept_ids,
        "condition_start_date": pd.to_datetime(stg_conditions["START"]).dt.date,
        "condition_start_datetime": pd.to_datetime(stg_conditions["START"]),
        "condition_end_date": pd.to_datetime(stg_conditions["STOP"]).dt.date,
        "condition_type_concept_id": TYPE_CONCEPT["ehr"],
        "condition_source_value": stg_conditions["CODE"].astype(str),
        "condition_source_concept_id": source_concept_ids,
        "visit_occurrence_id": stg_conditions["ENCOUNTER"].map(visit_lookup).fillna(0).astype(int),
    })

    conditions = conditions[conditions["person_id"] != 0]
    conditions = _generate_ids(conditions, "condition_occurrence_id")
    logger.info(f"  Produced {len(conditions):,} condition_occurrence records")
    return conditions


def transform_drug_exposure(
    stg_medications: pd.DataFrame,
    person_lookup: dict[str, int],
    visit_lookup: dict[str, int],
    mapper: VocabularyMapper,
) -> pd.DataFrame:
    """Synthea medications -> OMOP drug_exposure.

    Resolves RxNorm codes to standard concept_ids.
    """
    logger.info(f"Transforming {len(stg_medications):,} medications to drug_exposure")

    concept_ids = []
    source_concept_ids = []
    for code in stg_medications["CODE"].astype(str):
        source_id, standard_id = mapper.resolve(code, "RxNorm")
        source_concept_ids.append(source_id)
        concept_ids.append(standard_id)

    start_datetime = pd.to_datetime(stg_medications["START"])
    # OMOP requires drug_exposure_end_date — unlike Synthea's own STOP column,
    # it can't be left blank for a still-active prescription. Falling back to
    # the start date alone would record every still-open prescription as a
    # single day long, which is wrong in the same direction real pharmacy
    # claims data is wrong when days-supply is missing: it understates
    # exposure rather than guessing zero. DISPENSES (fill count) times a
    # standard 30-day fill is the conventional estimate when no explicit
    # days-supply is available — an ongoing metformin prescription refilled
    # 24 times reads as roughly two years of exposure, not one day.
    estimated_days_supply = pd.to_numeric(stg_medications["DISPENSES"], errors="coerce").fillna(1) * 30
    estimated_end = start_datetime + pd.to_timedelta(estimated_days_supply, unit="D")
    end_datetime = pd.to_datetime(stg_medications["STOP"]).fillna(estimated_end)

    drugs = pd.DataFrame({
        "person_id": stg_medications["PATIENT"].map(person_lookup).fillna(0).astype(int),
        "drug_concept_id": concept_ids,
        "drug_exposure_start_date": start_datetime.dt.date,
        "drug_exposure_start_datetime": start_datetime,
        "drug_exposure_end_date": end_datetime.dt.date,
        "drug_exposure_end_datetime": end_datetime,
        "verbatim_end_date": pd.to_datetime(stg_medications["STOP"]).dt.date,
        "drug_type_concept_id": TYPE_CONCEPT["prescription"],
        "quantity": stg_medications["DISPENSES"],
        "drug_source_value": stg_medications["CODE"].astype(str),
        "drug_source_concept_id": source_concept_ids,
        "visit_occurrence_id": stg_medications["ENCOUNTER"].map(visit_lookup).fillna(0).astype(int),
    })

    drugs = drugs[drugs["person_id"] != 0]
    drugs = _generate_ids(drugs, "drug_exposure_id")
    logger.info(f"  Produced {len(drugs):,} drug_exposure records")
    return drugs


def transform_observation_period(visits: pd.DataFrame) -> pd.DataFrame:
    """Derive one observation_period per person from their visit history.

    OMOP wants a period per person bounding the stretch of time they're
    presumed to be under observation — outside it, the absence of a condition
    or drug record can't be read as "didn't happen," just "wasn't looked at."
    The cleanest signal this pipeline has for that window is a patient's own
    encounter history: first visit to last visit. A person with no visits
    can't be given a period at all, so they're dropped here — they won't have
    downstream clinical events to bound anyway, since every condition/drug/
    measurement transform requires a visit_lookup hit.
    """
    logger.info(f"Deriving observation periods from {len(visits):,} visits")

    spans = visits.groupby("person_id").agg(
        observation_period_start_date=("visit_start_date", "min"),
        observation_period_end_date=("visit_end_date", "max"),
    ).reset_index()

    spans["period_type_concept_id"] = 44814724  # Period covering healthcare encounters

    periods = _generate_ids(spans, "observation_period_id")
    logger.info(f"  Produced {len(periods):,} observation_period records")
    return periods


def transform_death(stg_patients: pd.DataFrame, person_lookup: dict[str, int]) -> pd.DataFrame:
    """Synthea patients with a DEATHDATE -> OMOP death.

    Most patients in a Synthea population are still alive at generation time,
    so this is a small subset of stg_patients, not a 1:1 pass-through.
    """
    logger.info("Deriving death records from patient death dates")

    deceased = stg_patients[stg_patients["DEATHDATE"].notna()].copy()

    death = pd.DataFrame({
        "person_id": deceased["Id"].map(person_lookup).fillna(0).astype(int),
        "death_date": pd.to_datetime(deceased["DEATHDATE"]).dt.date,
        "death_datetime": pd.to_datetime(deceased["DEATHDATE"]),
        "death_type_concept_id": TYPE_CONCEPT["ehr"],
    })

    death = death[death["person_id"] != 0].reset_index(drop=True)
    logger.info(f"  Produced {len(death):,} death records")
    return death


def transform_procedure_occurrence(
    stg_procedures: pd.DataFrame,
    person_lookup: dict[str, int],
    visit_lookup: dict[str, int],
    mapper: VocabularyMapper,
) -> pd.DataFrame:
    """Synthea procedures -> OMOP procedure_occurrence.

    Synthea codes procedures in SNOMED CT, the same vocabulary as conditions,
    so this resolves through the same "SNOMED" lookup as
    transform_condition_occurrence.
    """
    logger.info(f"Transforming {len(stg_procedures):,} procedures to procedure_occurrence")

    concept_ids = []
    source_concept_ids = []
    for code in stg_procedures["CODE"].astype(str):
        source_id, standard_id = mapper.resolve(code, "SNOMED")
        source_concept_ids.append(source_id)
        concept_ids.append(standard_id)

    procedures = pd.DataFrame({
        "person_id": stg_procedures["PATIENT"].map(person_lookup).fillna(0).astype(int),
        "procedure_concept_id": concept_ids,
        "procedure_date": pd.to_datetime(stg_procedures["START"]).dt.date,
        "procedure_datetime": pd.to_datetime(stg_procedures["START"]),
        "procedure_type_concept_id": TYPE_CONCEPT["ehr"],
        "procedure_source_value": stg_procedures["CODE"].astype(str),
        "procedure_source_concept_id": source_concept_ids,
        "visit_occurrence_id": stg_procedures["ENCOUNTER"].map(visit_lookup).fillna(0).astype(int),
    })

    procedures = procedures[procedures["person_id"] != 0]
    procedures = _generate_ids(procedures, "procedure_occurrence_id")
    logger.info(f"  Produced {len(procedures):,} procedure_occurrence records")
    return procedures


def transform_observation(
    stg_observations: pd.DataFrame,
    person_lookup: dict[str, int],
    visit_lookup: dict[str, int],
    mapper: VocabularyMapper,
) -> pd.DataFrame:
    """Synthea observations (non-numeric) -> OMOP observation.

    The complement of transform_measurement: rows whose VALUE doesn't parse
    as a number — clinical notes coded as findings, categorical assessments,
    text lab results — go here as value_as_string instead of value_as_number.
    Splitting the two out this way is what OMOP itself does; measurement and
    observation aren't a Synthea distinction, they're a CDM one.
    """
    logger.info("Transforming non-numeric observations to observation")

    obs = stg_observations.copy()
    obs["value_numeric"] = pd.to_numeric(obs["VALUE"], errors="coerce")
    text_obs = obs[obs["value_numeric"].isna()].reset_index(drop=True)

    logger.info(f"  {len(text_obs):,} of {len(obs):,} observations are non-numeric")

    concept_ids = []
    source_concept_ids = []
    for code in text_obs["CODE"].astype(str):
        source_id, standard_id = mapper.resolve(code, "LOINC")
        source_concept_ids.append(source_id)
        concept_ids.append(standard_id)

    observations = pd.DataFrame({
        "person_id": text_obs["PATIENT"].map(person_lookup).fillna(0).astype(int),
        "observation_concept_id": concept_ids,
        "observation_date": pd.to_datetime(text_obs["DATE"]).dt.date,
        "observation_datetime": pd.to_datetime(text_obs["DATE"]),
        "observation_type_concept_id": TYPE_CONCEPT["ehr"],
        "value_as_string": text_obs["VALUE"].astype(str),
        "observation_source_value": text_obs["CODE"].astype(str),
        "observation_source_concept_id": source_concept_ids,
        "unit_source_value": text_obs["UNITS"],
        "visit_occurrence_id": text_obs["ENCOUNTER"].map(visit_lookup).fillna(0).astype(int),
    })

    observations = observations[observations["person_id"] != 0]
    observations = _generate_ids(observations, "observation_id")
    logger.info(f"  Produced {len(observations):,} observation records")
    return observations


def transform_measurement(
    stg_observations: pd.DataFrame,
    person_lookup: dict[str, int],
    visit_lookup: dict[str, int],
    mapper: VocabularyMapper,
) -> pd.DataFrame:
    """Synthea observations (numeric) -> OMOP measurement.

    Only rows with a parseable numeric VALUE become measurements. Text-valued
    observations go to the observation table instead.
    """
    logger.info("Transforming numeric observations to measurement")

    # Keep only rows where VALUE is numeric
    obs = stg_observations.copy()
    obs["value_numeric"] = pd.to_numeric(obs["VALUE"], errors="coerce")
    numeric_obs = obs[obs["value_numeric"].notna()].reset_index(drop=True)

    logger.info(f"  {len(numeric_obs):,} of {len(obs):,} observations are numeric")

    concept_ids = []
    source_concept_ids = []
    for code in numeric_obs["CODE"].astype(str):
        source_id, standard_id = mapper.resolve(code, "LOINC")
        source_concept_ids.append(source_id)
        concept_ids.append(standard_id)

    measurements = pd.DataFrame({
        "person_id": numeric_obs["PATIENT"].map(person_lookup).fillna(0).astype(int),
        "measurement_concept_id": concept_ids,
        "measurement_date": pd.to_datetime(numeric_obs["DATE"]).dt.date,
        "measurement_datetime": pd.to_datetime(numeric_obs["DATE"]),
        "measurement_type_concept_id": TYPE_CONCEPT["ehr"],
        "value_as_number": numeric_obs["value_numeric"],
        "unit_source_value": numeric_obs["UNITS"],
        "measurement_source_value": numeric_obs["CODE"].astype(str),
        "measurement_source_concept_id": source_concept_ids,
        "visit_occurrence_id": numeric_obs["ENCOUNTER"].map(visit_lookup).fillna(0).astype(int),
    })

    measurements = measurements[measurements["person_id"] != 0]
    measurements = _generate_ids(measurements, "measurement_id")
    logger.info(f"  Produced {len(measurements):,} measurement records")
    return measurements
