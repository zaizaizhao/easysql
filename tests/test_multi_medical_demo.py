"""Contract tests for the persistent EMR/PMS/RVS synthetic demo generator."""

from examples.multi_medical.init_db import (
    DATABASES,
    ONCOLOGY_PATIENT_COUNT,
    PATIENT_COUNT,
    _add_weekdays,
    _course_delivery_count,
    build_patients,
)


def test_demo_patient_generation_is_deterministic_and_synthetic() -> None:
    first = build_patients()
    second = build_patients()

    assert first == second
    assert len(first) == PATIENT_COUNT == 320
    assert len({patient.mpi_id for patient in first}) == PATIENT_COUNT
    assert len({patient.mrn for patient in first}) == PATIENT_COUNT
    assert all(patient.mpi_id.startswith("MPI-DEMO-") for patient in first)
    assert all(patient.id_token.startswith("DEMO-ID-") for patient in first)
    assert all("（虚构）" in patient.address for patient in first)


def test_demo_oncology_cohort_has_valid_fractionation_and_status_mix() -> None:
    oncology = [patient.oncology for patient in build_patients() if patient.oncology]

    assert len(oncology) == ONCOLOGY_PATIENT_COUNT == 96
    assert {seed.course_status for seed in oncology} == {
        "ACTIVE",
        "COMPLETED",
        "DISCONTINUED",
        "ON_HOLD",
        "READY",
    }
    assert len({seed.diagnosis_code for seed in oncology}) >= 8
    assert len({seed.technique for seed in oncology}) >= 4

    for seed in oncology:
        assert abs(seed.total_dose_gy - seed.fraction_count * seed.dose_per_fraction_gy) <= 0.2
        assert 0 <= _course_delivery_count(seed) <= seed.fraction_count


def test_demo_database_names_and_treatment_calendar_are_stable() -> None:
    assert DATABASES == ("emr_demo", "pms_demo", "rvs_demo")

    starts = [patient.oncology.planned_start_date for patient in build_patients() if patient.oncology]
    assert all(start.weekday() < 5 for start in starts)
    start = starts[0]
    next_treatment_day = _add_weekdays(start, 1)
    assert next_treatment_day > start
    assert next_treatment_day.weekday() < 5
