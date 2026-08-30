"""Create persistent EMR, patient portal, and radiotherapy demo databases.

The dataset is deterministic and entirely synthetic. The initializer refuses to
replace existing databases unless ``--recreate`` is explicitly provided.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, make_dsn
from psycopg2.extras import execute_values

DATABASES = ("emr_demo", "pms_demo", "rvs_demo")
QUERY_ROLE = os.getenv("DEMO_QUERY_USER", "easysql_demo_ro")
RANDOM_SEED = 20260829
PATIENT_COUNT = 320
ONCOLOGY_PATIENT_COUNT = 96
BASE_DIR = Path(__file__).resolve().parent

ADMIN_HOST = os.getenv("PGHOST", "127.0.0.1")
ADMIN_PORT = int(os.getenv("PGPORT", "55432"))
ADMIN_USER = os.getenv("PGUSER", "postgres")
ADMIN_PASSWORD = os.getenv("PGPASSWORD", "")
QUERY_PASSWORD = os.getenv("DEMO_QUERY_PASSWORD", "")
DBLINK_HOST = os.getenv("DEMO_DBLINK_HOST", "easysql-postgres")
DBLINK_PORT = os.getenv("DEMO_DBLINK_PORT", "5432")


@dataclass(frozen=True)
class OncologySeed:
    request_number: str
    course_uid: str
    diagnosis_code: str
    diagnosis_name: str
    site_code: str
    site_name: str
    laterality: str
    stage: str
    intent: str
    total_dose_gy: float
    fraction_count: int
    dose_per_fraction_gy: float
    technique: str
    image_guidance: str
    consult_date: date
    planned_start_date: date
    course_status: str


@dataclass(frozen=True)
class PatientSeed:
    sequence: int
    mpi_id: str
    mrn: str
    name: str
    gender: str
    birth_date: date
    id_token: str
    phone: str
    marital_status: str
    insurance_type: str
    province: str
    city: str
    district: str
    address: str
    registered_at: datetime
    oncology: OncologySeed | None


@dataclass
class EmrSeedResult:
    encounter_numbers: dict[str, list[str]]
    oncology_encounters: dict[str, str]


def _admin_connection(database: str = "postgres") -> Any:
    return psycopg2.connect(
        host=ADMIN_HOST,
        port=ADMIN_PORT,
        user=ADMIN_USER,
        password=ADMIN_PASSWORD,
        dbname=database,
    )


def _query_connection(database: str) -> Any:
    return psycopg2.connect(
        host=ADMIN_HOST,
        port=ADMIN_PORT,
        user=QUERY_ROLE,
        password=QUERY_PASSWORD,
        dbname=database,
    )


def _insert_many(
    connection: Any,
    table: str,
    columns: tuple[str, ...],
    rows: list[tuple[Any, ...]],
) -> None:
    if not rows:
        return
    statement = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )
    with connection.cursor() as cursor:
        execute_values(cursor, statement.as_string(connection), rows, page_size=1000)


def _fetch_map(connection: Any, table: str, key_column: str, id_column: str) -> dict[str, int]:
    statement = sql.SQL("SELECT {}, {} FROM {}").format(
        sql.Identifier(key_column),
        sql.Identifier(id_column),
        sql.Identifier(table),
    )
    with connection.cursor() as cursor:
        cursor.execute(statement)
        return {str(key): int(identifier) for key, identifier in cursor.fetchall()}


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=minute))


def _add_weekdays(start: date, offset: int) -> date:
    current = start
    remaining = offset
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _next_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _course_delivery_count(seed: OncologySeed) -> int:
    if seed.course_status == "COMPLETED":
        return seed.fraction_count
    if seed.course_status == "ACTIVE":
        return max(3, int(seed.fraction_count * 0.58))
    if seed.course_status == "ON_HOLD":
        return max(2, int(seed.fraction_count * 0.42))
    if seed.course_status == "DISCONTINUED":
        return max(1, int(seed.fraction_count * 0.30))
    return 0


def _oncology_seed(sequence: int) -> OncologySeed:
    profiles = (
        (
            "C34.9",
            "肺恶性肿瘤",
            "LUNG",
            "肺",
            "RIGHT",
            "IIIA",
            "CURATIVE",
            60.0,
            30,
            2.0,
            "VMAT",
            "DAILY_CBCT",
        ),
        (
            "C50.9",
            "乳腺恶性肿瘤",
            "BREAST",
            "乳腺",
            "LEFT",
            "IIA",
            "ADJUVANT",
            40.05,
            15,
            2.67,
            "IMRT",
            "WEEKLY_KV",
        ),
        (
            "C61",
            "前列腺恶性肿瘤",
            "PROSTATE",
            "前列腺",
            "NOT_APPLICABLE",
            "IIC",
            "CURATIVE",
            60.0,
            20,
            3.0,
            "VMAT",
            "DAILY_CBCT",
        ),
        (
            "C20",
            "直肠恶性肿瘤",
            "RECTUM",
            "直肠",
            "NOT_APPLICABLE",
            "IIIB",
            "NEOADJUVANT",
            50.4,
            28,
            1.8,
            "IMRT",
            "DAILY_CBCT",
        ),
        (
            "C11.9",
            "鼻咽恶性肿瘤",
            "NASOPHARYNX",
            "鼻咽",
            "MIDLINE",
            "III",
            "CURATIVE",
            69.96,
            33,
            2.12,
            "VMAT",
            "DAILY_CBCT",
        ),
        (
            "C79.3",
            "脑继发恶性肿瘤",
            "BRAIN",
            "脑",
            "MIDLINE",
            "IV",
            "PALLIATIVE",
            30.0,
            10,
            3.0,
            "3DCRT",
            "DAILY_KV",
        ),
        (
            "C53.9",
            "宫颈恶性肿瘤",
            "CERVIX",
            "宫颈",
            "MIDLINE",
            "IIB",
            "CURATIVE",
            50.4,
            28,
            1.8,
            "VMAT",
            "DAILY_CBCT",
        ),
        (
            "C15.9",
            "食管恶性肿瘤",
            "ESOPHAGUS",
            "食管",
            "MIDLINE",
            "IIIA",
            "CURATIVE",
            50.4,
            28,
            1.8,
            "IMRT",
            "DAILY_CBCT",
        ),
        (
            "C22.0",
            "肝细胞癌",
            "LIVER",
            "肝",
            "RIGHT",
            "II",
            "CURATIVE",
            50.0,
            10,
            5.0,
            "SBRT",
            "DAILY_CBCT",
        ),
        (
            "C71.9",
            "脑恶性肿瘤",
            "BRAIN",
            "脑",
            "MIDLINE",
            "IV",
            "ADJUVANT",
            60.0,
            30,
            2.0,
            "IMRT",
            "DAILY_KV",
        ),
    )
    profile = profiles[(sequence - 1) % len(profiles)]

    if sequence <= 56:
        status = "COMPLETED"
        consult = date(2024, 3, 4) + timedelta(days=(sequence - 1) * 8)
        start = consult + timedelta(days=21)
    elif sequence <= 76:
        status = "ACTIVE"
        consult = date(2026, 5, 5) + timedelta(days=(sequence - 57) * 3)
        start = date(2026, 7, 20) + timedelta(days=(sequence - 57) % 8)
    elif sequence <= 84:
        status = "ON_HOLD"
        consult = date(2026, 5, 20) + timedelta(days=(sequence - 77) * 4)
        start = date(2026, 7, 27) + timedelta(days=(sequence - 77) % 5)
    elif sequence <= 90:
        status = "READY"
        consult = date(2026, 7, 6) + timedelta(days=(sequence - 85) * 5)
        start = date(2026, 9, 7) + timedelta(days=(sequence - 85) * 2)
    else:
        status = "DISCONTINUED"
        consult = date(2025, 10, 6) + timedelta(days=(sequence - 91) * 9)
        start = consult + timedelta(days=18)

    return OncologySeed(
        request_number=f"SR-RT-{sequence:06d}",
        course_uid=f"RTCOURSE-DEMO-{sequence:06d}",
        diagnosis_code=profile[0],
        diagnosis_name=profile[1],
        site_code=profile[2],
        site_name=profile[3],
        laterality=profile[4],
        stage=profile[5],
        intent=profile[6],
        total_dose_gy=profile[7],
        fraction_count=profile[8],
        dose_per_fraction_gy=profile[9],
        technique=profile[10],
        image_guidance=profile[11],
        consult_date=consult,
        planned_start_date=_next_weekday(start),
        course_status=status,
    )


def build_patients() -> list[PatientSeed]:
    rng = random.Random(RANDOM_SEED)
    surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    given_names = (
        "伟",
        "芳",
        "娜",
        "敏",
        "静",
        "丽",
        "强",
        "磊",
        "军",
        "洋",
        "勇",
        "艳",
        "杰",
        "娟",
        "涛",
        "明",
        "超",
        "秀英",
        "霞",
        "平",
        "刚",
        "桂英",
        "丹",
        "萍",
        "鹏",
        "华",
        "红",
        "玉兰",
        "飞",
        "宇",
    )
    cities = (
        ("浙江省", "杭州市", "滨江区"),
        ("江苏省", "南京市", "鼓楼区"),
        ("上海市", "上海市", "浦东新区"),
        ("广东省", "广州市", "越秀区"),
        ("四川省", "成都市", "武侯区"),
        ("湖北省", "武汉市", "江汉区"),
        ("山东省", "济南市", "历下区"),
        ("北京市", "北京市", "海淀区"),
    )
    insurance_types = ("URRBMI", "UEBMI", "SELF_PAY", "COMMERCIAL")
    marital_statuses = ("MARRIED", "SINGLE", "DIVORCED", "WIDOWED")
    patients: list[PatientSeed] = []

    for sequence in range(1, PATIENT_COUNT + 1):
        oncology = _oncology_seed(sequence) if sequence <= ONCOLOGY_PATIENT_COUNT else None
        gender = "M" if sequence % 2 else "F"
        if oncology:
            age = rng.randint(42, 79)
        else:
            age = rng.randint(18, 82)
        birth = date(2026 - age, rng.randint(1, 12), rng.randint(1, 28))
        province, city, district = cities[(sequence - 1) % len(cities)]
        name = f"{surnames[(sequence - 1) % len(surnames)]}{given_names[(sequence * 7) % len(given_names)]}"
        registered = datetime(2023, 1, 1, 9) + timedelta(days=(sequence * 11) % 900)
        patients.append(
            PatientSeed(
                sequence=sequence,
                mpi_id=f"MPI-DEMO-{sequence:06d}",
                mrn=f"MRN2026{sequence:06d}",
                name=name,
                gender=gender,
                birth_date=birth,
                id_token=f"DEMO-ID-{sequence:06d}",
                phone=f"1380000{sequence:04d}",
                marital_status=marital_statuses[sequence % len(marital_statuses)],
                insurance_type=insurance_types[sequence % len(insurance_types)],
                province=province,
                city=city,
                district=district,
                address=f"{district}演示路{sequence % 120 + 1}号（虚构）",
                registered_at=registered,
                oncology=oncology,
            )
        )
    return patients


def create_role_and_databases(recreate: bool) -> None:
    if not ADMIN_PASSWORD:
        raise RuntimeError("PGPASSWORD is required for the PostgreSQL administrator")
    if not QUERY_PASSWORD:
        raise RuntimeError("DEMO_QUERY_PASSWORD is required and will not be printed")

    connection = _admin_connection()
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (QUERY_ROLE,))
            if cursor.fetchone():
                cursor.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD %s").format(
                        sql.Identifier(QUERY_ROLE)
                    ),
                    (QUERY_PASSWORD,),
                )
            else:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD %s").format(
                        sql.Identifier(QUERY_ROLE)
                    ),
                    (QUERY_PASSWORD,),
                )

            for database in DATABASES:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
                exists = cursor.fetchone() is not None
                if exists and not recreate:
                    raise RuntimeError(
                        f"Database '{database}' already exists; pass --recreate to replace demo data"
                    )
                if exists:
                    cursor.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (database,),
                    )
                    cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
                cursor.execute(
                    sql.SQL("CREATE DATABASE {} WITH ENCODING 'UTF8'").format(
                        sql.Identifier(database)
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(database), sql.Identifier(QUERY_ROLE)
                    )
                )
    finally:
        connection.close()


def apply_schema(database: str, filename: str) -> None:
    connection = _admin_connection(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute((BASE_DIR / filename).read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


def seed_emr(patients: list[PatientSeed]) -> EmrSeedResult:
    connection = _admin_connection("emr_demo")
    encounter_numbers: dict[str, list[str]] = {patient.mpi_id: [] for patient in patients}
    oncology_encounters: dict[str, str] = {}
    try:
        _insert_many(
            connection,
            "organization",
            (
                "organization_code",
                "organization_name",
                "organization_type",
                "province",
                "city",
                "active",
            ),
            [
                (
                    "HOSP-DEMO-001",
                    "华东肿瘤诊疗中心（演示）",
                    "TERTIARY_HOSPITAL",
                    "浙江省",
                    "杭州市",
                    True,
                )
            ],
        )
        departments = (
            ("ONCOLOGY", "肿瘤内科", "ONC", True, True),
            ("RADIATION_ONCOLOGY", "放射治疗科", "RADONC", True, True),
            ("RESPIRATORY", "呼吸内科", "RESP", True, True),
            ("BREAST_SURGERY", "乳腺外科", "BREAST", True, True),
            ("GASTROENTEROLOGY", "消化内科", "GI", True, True),
            ("UROLOGY", "泌尿外科", "URO", True, True),
            ("NEUROSURGERY", "神经外科", "NEURO", True, True),
            ("EMERGENCY", "急诊医学科", "EM", True, False),
            ("IMAGING", "医学影像科", "RAD", False, False),
            ("PATHOLOGY", "病理科", "PATH", False, False),
        )
        _insert_many(
            connection,
            "department",
            (
                "organization_id",
                "department_code",
                "department_name",
                "specialty_code",
                "outpatient_enabled",
                "inpatient_enabled",
                "active",
            ),
            [(1, *department, True) for department in departments],
        )
        department_ids = _fetch_map(connection, "department", "department_code", "department_id")

        practitioner_rows: list[tuple[Any, ...]] = []
        titles = ("主任医师", "副主任医师", "主治医师", "住院医师")
        practitioner_sequence = 1
        for department_code, department_name, *_ in departments:
            count = 4 if department_code in {"ONCOLOGY", "RADIATION_ONCOLOGY"} else 2
            for local_index in range(count):
                practitioner_rows.append(
                    (
                        f"DOC-{practitioner_sequence:04d}",
                        f"演示医师{practitioner_sequence:02d}",
                        department_ids[department_code],
                        titles[local_index % len(titles)],
                        department_name,
                        f"DEMO-LICENSE-{practitioner_sequence:04d}",
                        True,
                    )
                )
                practitioner_sequence += 1
        _insert_many(
            connection,
            "practitioner",
            (
                "practitioner_no",
                "practitioner_name",
                "department_id",
                "professional_title",
                "specialty",
                "license_token",
                "active",
            ),
            practitioner_rows,
        )
        practitioner_ids = _fetch_map(
            connection, "practitioner", "practitioner_no", "practitioner_id"
        )
        practitioners_by_department: dict[str, list[str]] = {}
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT d.department_code, p.practitioner_no FROM practitioner p "
                "JOIN department d ON d.department_id = p.department_id ORDER BY p.practitioner_id"
            )
            for department_code, practitioner_no in cursor.fetchall():
                practitioners_by_department.setdefault(department_code, []).append(practitioner_no)

        _insert_many(
            connection,
            "patient",
            (
                "mpi_id",
                "medical_record_number",
                "patient_name",
                "gender_code",
                "birth_date",
                "id_document_token",
                "mobile_phone",
                "marital_status",
                "insurance_type_code",
                "province",
                "city",
                "district",
                "address_text",
                "registered_at",
                "active",
                "synthetic_identity",
            ),
            [
                (
                    patient.mpi_id,
                    patient.mrn,
                    patient.name,
                    patient.gender,
                    patient.birth_date,
                    patient.id_token,
                    patient.phone,
                    patient.marital_status,
                    patient.insurance_type,
                    patient.province,
                    patient.city,
                    patient.district,
                    patient.address,
                    patient.registered_at,
                    True,
                    True,
                )
                for patient in patients
            ],
        )
        patient_ids = _fetch_map(connection, "patient", "mpi_id", "patient_id")
        identifier_rows: list[tuple[Any, ...]] = []
        for patient in patients:
            identifier_rows.extend(
                [
                    (
                        patient_ids[patient.mpi_id],
                        "urn:easysql:mpi",
                        patient.mpi_id,
                        "OFFICIAL",
                        patient.registered_at.date(),
                        None,
                    ),
                    (
                        patient_ids[patient.mpi_id],
                        "urn:easysql:mrn",
                        patient.mrn,
                        "USUAL",
                        patient.registered_at.date(),
                        None,
                    ),
                    (
                        patient_ids[patient.mpi_id],
                        "urn:easysql:insurance-demo",
                        f"INS-DEMO-{patient.sequence:08d}",
                        "SECONDARY",
                        patient.registered_at.date(),
                        None,
                    ),
                ]
            )
        _insert_many(
            connection,
            "patient_identifier",
            (
                "patient_id",
                "identifier_system",
                "identifier_value",
                "identifier_use",
                "valid_from",
                "valid_to",
            ),
            identifier_rows,
        )

        general_diagnoses = (
            ("I10", "原发性高血压", "RESPIRATORY", "血压升高复诊"),
            ("E11.9", "2型糖尿病", "GASTROENTEROLOGY", "血糖控制随访"),
            ("J06.9", "急性上呼吸道感染", "RESPIRATORY", "咳嗽伴咽痛"),
            ("K29.7", "胃炎", "GASTROENTEROLOGY", "上腹不适"),
            ("M54.5", "下背痛", "EMERGENCY", "腰部疼痛"),
        )
        encounter_rows: list[tuple[Any, ...]] = []
        encounter_context: dict[str, tuple[PatientSeed, str, datetime, str, str]] = {}
        for patient in patients:
            general_count = 2 + patient.sequence % 4
            for local_index in range(1, general_count + 1):
                diagnosis_code, _, department_code, complaint = general_diagnoses[
                    (patient.sequence + local_index) % len(general_diagnoses)
                ]
                day = date(2024, 1, 2) + timedelta(
                    days=(patient.sequence * 13 + local_index * 47) % 820
                )
                start = _at(day, 8 + (patient.sequence + local_index) % 8, (local_index * 10) % 60)
                encounter_class = (
                    "INPATIENT" if (patient.sequence + local_index) % 23 == 0 else "OUTPATIENT"
                )
                if (patient.sequence + local_index) % 41 == 0:
                    encounter_class = "EMERGENCY"
                    department_code = "EMERGENCY"
                encounter_number = f"ENC-{patient.sequence:06d}-{local_index:02d}"
                practitioner_no = practitioners_by_department[department_code][
                    (patient.sequence + local_index)
                    % len(practitioners_by_department[department_code])
                ]
                end = start + (
                    timedelta(days=3, hours=2)
                    if encounter_class == "INPATIENT"
                    else timedelta(minutes=35)
                )
                encounter_rows.append(
                    (
                        encounter_number,
                        patient_ids[patient.mpi_id],
                        encounter_class,
                        "FINISHED",
                        department_ids[department_code],
                        practitioner_ids[practitioner_no],
                        start,
                        end,
                        complaint,
                        "SELF",
                        "HOME",
                        f"APT-GEN-{patient.sequence:06d}-{local_index:02d}",
                        start - timedelta(days=3),
                    )
                )
                encounter_numbers[patient.mpi_id].append(encounter_number)
                encounter_context[encounter_number] = (
                    patient,
                    diagnosis_code,
                    start,
                    department_code,
                    practitioner_no,
                )

            if patient.oncology:
                oncology = patient.oncology
                start = _at(oncology.consult_date, 9 + patient.sequence % 6, 20)
                encounter_number = f"ENC-ONC-{patient.sequence:06d}"
                practitioner_no = practitioners_by_department["RADIATION_ONCOLOGY"][
                    patient.sequence % 4
                ]
                encounter_rows.append(
                    (
                        encounter_number,
                        patient_ids[patient.mpi_id],
                        "OUTPATIENT",
                        "FINISHED",
                        department_ids["RADIATION_ONCOLOGY"],
                        practitioner_ids[practitioner_no],
                        start,
                        start + timedelta(minutes=60),
                        f"{oncology.diagnosis_name}放射治疗评估",
                        "REFERRAL",
                        "HOME",
                        f"APT-RTCONS-{patient.sequence:06d}",
                        start - timedelta(days=5),
                    )
                )
                encounter_numbers[patient.mpi_id].append(encounter_number)
                oncology_encounters[patient.mpi_id] = encounter_number
                encounter_context[encounter_number] = (
                    patient,
                    oncology.diagnosis_code,
                    start,
                    "RADIATION_ONCOLOGY",
                    practitioner_no,
                )

        _insert_many(
            connection,
            "encounter",
            (
                "encounter_number",
                "patient_id",
                "encounter_class",
                "encounter_status",
                "department_id",
                "attending_practitioner_id",
                "start_at",
                "end_at",
                "chief_complaint",
                "admission_source",
                "discharge_disposition",
                "source_appointment_number",
                "created_at",
            ),
            encounter_rows,
        )
        encounter_ids = _fetch_map(connection, "encounter", "encounter_number", "encounter_id")

        diagnosis_rows: list[tuple[Any, ...]] = []
        diagnosis_sequence = 1
        for encounter_number, (
            patient,
            diagnosis_code,
            start,
            _department_code,
            practitioner_no,
        ) in encounter_context.items():
            if patient.oncology and encounter_number == oncology_encounters.get(patient.mpi_id):
                oncology = patient.oncology
                diagnosis_name = oncology.diagnosis_name
                stage = oncology.stage
                t_stage = ("T2", "T3", "T4")[patient.sequence % 3]
                n_stage = ("N0", "N1", "N2")[patient.sequence % 3]
                m_stage = "M1" if oncology.intent == "PALLIATIVE" else "M0"
                diagnosis_type = "PRIMARY"
            else:
                match = next(item for item in general_diagnoses if item[0] == diagnosis_code)
                diagnosis_name = match[1]
                stage = t_stage = n_stage = m_stage = None
                diagnosis_type = "PRIMARY"
            diagnosis_rows.append(
                (
                    patient_ids[patient.mpi_id],
                    encounter_ids[encounter_number],
                    "ICD-10",
                    diagnosis_code,
                    diagnosis_name,
                    diagnosis_type,
                    "ACTIVE",
                    start.date() - timedelta(days=10),
                    stage,
                    t_stage,
                    n_stage,
                    m_stage,
                    start,
                    practitioner_ids[practitioner_no],
                )
            )
            diagnosis_sequence += 1
            if patient.sequence % 3 == 0:
                comorbidity = general_diagnoses[patient.sequence % 2]
                diagnosis_rows.append(
                    (
                        patient_ids[patient.mpi_id],
                        encounter_ids[encounter_number],
                        "ICD-10",
                        comorbidity[0],
                        comorbidity[1],
                        "COMORBIDITY",
                        "ACTIVE",
                        patient.birth_date + timedelta(days=15000),
                        None,
                        None,
                        None,
                        None,
                        start,
                        practitioner_ids[practitioner_no],
                    )
                )
                diagnosis_sequence += 1
        _insert_many(
            connection,
            "diagnosis",
            (
                "patient_id",
                "encounter_id",
                "code_system",
                "diagnosis_code",
                "diagnosis_name",
                "diagnosis_type",
                "clinical_status",
                "onset_date",
                "stage_group",
                "t_stage",
                "n_stage",
                "m_stage",
                "recorded_at",
                "verified_by_practitioner_id",
            ),
            diagnosis_rows,
        )

        pathology_rows: list[tuple[Any, ...]] = []
        for patient in patients[:ONCOLOGY_PATIENT_COUNT]:
            oncology = patient.oncology
            assert oncology is not None
            if oncology.diagnosis_code in {"C79.3"}:
                continue
            report_date = oncology.consult_date - timedelta(days=12)
            is_breast = oncology.diagnosis_code == "C50.9"
            pathology_rows.append(
                (
                    f"PATH-DEMO-{patient.sequence:06d}",
                    patient_ids[patient.mpi_id],
                    encounter_ids[oncology_encounters[patient.mpi_id]],
                    "穿刺活检组织",
                    report_date - timedelta(days=4),
                    report_date,
                    "8140/3",
                    "浸润性恶性肿瘤",
                    ("G1", "G2", "G3")[patient.sequence % 3],
                    "POSITIVE" if is_breast and patient.sequence % 3 else "NEGATIVE",
                    "POSITIVE" if is_breast and patient.sequence % 4 else "NEGATIVE",
                    ("0", "1+", "2+", "3+")[patient.sequence % 4] if is_breast else None,
                    float(15 + patient.sequence % 55) if is_breast else None,
                    float(patient.sequence % 30) if oncology.diagnosis_code == "C34.9" else None,
                    f"病理形态符合{oncology.diagnosis_name}，本报告为虚构演示数据。",
                )
            )
        _insert_many(
            connection,
            "pathology_report",
            (
                "pathology_number",
                "patient_id",
                "encounter_id",
                "specimen_type",
                "collection_date",
                "report_date",
                "histology_code",
                "histology_name",
                "differentiation_grade",
                "er_result",
                "pr_result",
                "her2_result",
                "ki67_percent",
                "pdl1_cps",
                "conclusion",
            ),
            pathology_rows,
        )

        allergy_options = (
            ("PENICILLIN", "青霉素", "ALLERGY", "HIGH", "皮疹"),
            ("CEPHALOSPORIN", "头孢菌素", "ALLERGY", "HIGH", "荨麻疹"),
            ("IODINATED_CONTRAST", "含碘对比剂", "ALLERGY", "HIGH", "呼吸困难"),
            ("LACTOSE", "乳糖", "INTOLERANCE", "LOW", "腹胀"),
        )
        allergy_rows = []
        for patient in patients:
            if patient.sequence % 4 == 0:
                option = allergy_options[patient.sequence % len(allergy_options)]
                allergy_rows.append(
                    (patient_ids[patient.mpi_id], *option, "ACTIVE", patient.registered_at)
                )
        _insert_many(
            connection,
            "allergy_intolerance",
            (
                "patient_id",
                "substance_code",
                "substance_name",
                "allergy_type",
                "criticality",
                "reaction_text",
                "clinical_status",
                "recorded_at",
            ),
            allergy_rows,
        )

        medication_options = (
            ("AMLODIPINE", "氨氯地平", 5.0, "mg", "PO", "QD"),
            ("METFORMIN", "二甲双胍", 500.0, "mg", "PO", "BID"),
            ("OMEPRAZOLE", "奥美拉唑", 20.0, "mg", "PO", "QD"),
            ("ONDANSETRON", "昂丹司琼", 8.0, "mg", "PO", "PRN"),
        )
        medication_rows: list[tuple[Any, ...]] = []
        observation_rows: list[tuple[Any, ...]] = []
        procedure_rows: list[tuple[Any, ...]] = []
        imaging_rows: list[tuple[Any, ...]] = []
        document_rows: list[tuple[Any, ...]] = []
        service_rows: list[tuple[Any, ...]] = []
        medication_sequence = observation_sequence = procedure_sequence = imaging_sequence = (
            document_sequence
        ) = 1

        for patient in patients:
            latest_encounter_number = encounter_numbers[patient.mpi_id][-1]
            latest_encounter_id = encounter_ids[latest_encounter_number]
            latest_context = encounter_context[latest_encounter_number]
            practitioner_no = latest_context[4]
            latest_time = latest_context[2]
            medication_count = 1 + patient.sequence % 2
            for local_index in range(medication_count):
                medication = medication_options[
                    (patient.sequence + local_index) % len(medication_options)
                ]
                medication_rows.append(
                    (
                        f"MEDORD-{medication_sequence:08d}",
                        patient_ids[patient.mpi_id],
                        latest_encounter_id,
                        medication[0],
                        medication[1],
                        medication[2],
                        medication[3],
                        medication[4],
                        medication[5],
                        latest_time,
                        latest_time + timedelta(days=14),
                        "COMPLETED",
                        practitioner_ids[practitioner_no],
                    )
                )
                medication_sequence += 1

            observations = (
                ("VITAL_SIGNS", "8480-6", "收缩压", 105 + patient.sequence % 45, "mmHg", 90, 140),
                ("VITAL_SIGNS", "8462-4", "舒张压", 65 + patient.sequence % 30, "mmHg", 60, 90),
                (
                    "LABORATORY",
                    "6690-2",
                    "白细胞计数",
                    round(3.5 + (patient.sequence % 45) / 10, 1),
                    "10^9/L",
                    3.5,
                    9.5,
                ),
                ("LABORATORY", "718-7", "血红蛋白", 105 + patient.sequence % 55, "g/L", 115, 150),
                ("PERFORMANCE_STATUS", "ECOG", "ECOG体能状态", patient.sequence % 3, "score", 0, 2),
            )
            for observation in observations:
                value = float(observation[3])
                low = float(observation[5])
                high = float(observation[6])
                flag = "L" if value < low else "H" if value > high else "N"
                observation_rows.append(
                    (
                        f"OBS-{observation_sequence:09d}",
                        patient_ids[patient.mpi_id],
                        latest_encounter_id,
                        observation[0],
                        observation[1],
                        observation[2],
                        value,
                        None,
                        observation[4],
                        low,
                        high,
                        flag,
                        latest_time + timedelta(minutes=10),
                        "FINAL",
                    )
                )
                observation_sequence += 1

            procedure_rows.append(
                (
                    f"PROC-{procedure_sequence:08d}",
                    patient_ids[patient.mpi_id],
                    latest_encounter_id,
                    "99.29",
                    "诊疗处置",
                    None,
                    None,
                    "COMPLETED",
                    latest_time + timedelta(minutes=15),
                    latest_time + timedelta(minutes=35),
                    practitioner_ids[practitioner_no],
                    "处置完成，无即刻并发症",
                )
            )
            procedure_sequence += 1

            for encounter_number in encounter_numbers[patient.mpi_id]:
                context = encounter_context[encounter_number]
                document_rows.append(
                    (
                        f"DOC-{document_sequence:09d}",
                        patient_ids[patient.mpi_id],
                        encounter_ids[encounter_number],
                        "OUTPATIENT_NOTE",
                        f"{context[3]}就诊记录",
                        "FINAL",
                        context[2] + timedelta(minutes=40),
                        practitioner_ids[context[4]],
                        f"患者因{context[1]}相关问题就诊，完成评估与处置。全部为演示文本。",
                    )
                )
                document_sequence += 1

            if patient.oncology:
                oncology = patient.oncology
                onc_encounter_id = encounter_ids[oncology_encounters[patient.mpi_id]]
                onc_time = _at(oncology.consult_date, 10)
                imaging_rows.append(
                    (
                        f"ACC-DEMO-{imaging_sequence:06d}",
                        patient_ids[patient.mpi_id],
                        onc_encounter_id,
                        "CT",
                        oncology.site_name,
                        oncology.consult_date - timedelta(days=8),
                        "FINAL",
                        f"{oncology.site_name}可见占位性病变，测量值为合成演示结果。",
                        f"结合临床考虑{oncology.diagnosis_name}，建议分期评估。",
                        practitioner_ids[
                            practitioners_by_department["IMAGING"][patient.sequence % 2]
                        ],
                        f"1.2.826.0.1.3680043.10.999.1.{patient.sequence}",
                    )
                )
                imaging_sequence += 1
                service_rows.append(
                    (
                        oncology.request_number,
                        patient_ids[patient.mpi_id],
                        onc_encounter_id,
                        "RADIOTHERAPY_TREATMENT",
                        "RT-TREAT",
                        "放射治疗",
                        "ROUTINE",
                        (
                            "COMPLETED"
                            if oncology.course_status in {"COMPLETED", "DISCONTINUED"}
                            else "ACTIVE"
                        ),
                        onc_time,
                        oncology.planned_start_date,
                        oncology.diagnosis_code,
                        f"{oncology.diagnosis_name}，{oncology.stage}期，拟行{oncology.technique}",
                        practitioner_ids[
                            practitioners_by_department["RADIATION_ONCOLOGY"][patient.sequence % 4]
                        ],
                        "RVS",
                    )
                )

        _insert_many(
            connection,
            "medication_order",
            (
                "order_number",
                "patient_id",
                "encounter_id",
                "medication_code",
                "medication_name",
                "dose_value",
                "dose_unit",
                "route_code",
                "frequency_code",
                "start_at",
                "end_at",
                "order_status",
                "prescribing_practitioner_id",
            ),
            medication_rows,
        )
        _insert_many(
            connection,
            "observation",
            (
                "observation_number",
                "patient_id",
                "encounter_id",
                "category_code",
                "observation_code",
                "observation_name",
                "value_numeric",
                "value_text",
                "unit",
                "reference_range_low",
                "reference_range_high",
                "abnormal_flag",
                "effective_at",
                "status",
            ),
            observation_rows,
        )
        _insert_many(
            connection,
            "procedure_record",
            (
                "procedure_number",
                "patient_id",
                "encounter_id",
                "procedure_code",
                "procedure_name",
                "body_site_code",
                "body_site_name",
                "procedure_status",
                "performed_start_at",
                "performed_end_at",
                "performer_practitioner_id",
                "outcome_text",
            ),
            procedure_rows,
        )
        _insert_many(
            connection,
            "imaging_report",
            (
                "accession_number",
                "patient_id",
                "encounter_id",
                "modality",
                "body_site",
                "study_date",
                "report_status",
                "findings",
                "impression",
                "reporting_practitioner_id",
                "dicom_study_instance_uid",
            ),
            imaging_rows,
        )
        _insert_many(
            connection,
            "clinical_document",
            (
                "document_number",
                "patient_id",
                "encounter_id",
                "document_type",
                "document_title",
                "document_status",
                "authored_at",
                "author_practitioner_id",
                "summary_text",
            ),
            document_rows,
        )
        _insert_many(
            connection,
            "service_request",
            (
                "request_number",
                "patient_id",
                "encounter_id",
                "request_type",
                "service_code",
                "service_name",
                "priority",
                "request_status",
                "authored_at",
                "requested_start_date",
                "reason_code",
                "reason_text",
                "requesting_practitioner_id",
                "destination_system",
            ),
            service_rows,
        )
        connection.commit()
        return EmrSeedResult(
            encounter_numbers=encounter_numbers, oncology_encounters=oncology_encounters
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def seed_pms(patients: list[PatientSeed], emr_result: EmrSeedResult) -> None:
    connection = _admin_connection("pms_demo")
    try:
        account_patients = patients[:280]
        _insert_many(
            connection,
            "portal_account",
            (
                "account_number",
                "mpi_id",
                "emr_medical_record_number",
                "display_name",
                "mobile_phone",
                "email",
                "identity_verified",
                "verification_level",
                "preferred_language",
                "account_status",
                "registered_at",
                "last_login_at",
                "synthetic_identity",
            ),
            [
                (
                    f"PORTAL-{patient.sequence:06d}",
                    patient.mpi_id,
                    patient.mrn,
                    patient.name,
                    patient.phone,
                    f"patient{patient.sequence:04d}@example.invalid",
                    patient.sequence % 9 != 0,
                    "REAL_NAME_VERIFIED" if patient.sequence % 9 != 0 else "MOBILE_VERIFIED",
                    "zh-CN",
                    "ACTIVE" if patient.sequence % 31 else "LOCKED",
                    patient.registered_at + timedelta(days=2),
                    datetime(2026, 8, 20, 8) + timedelta(hours=patient.sequence % 120),
                    True,
                )
                for patient in account_patients
            ],
        )
        account_ids = _fetch_map(connection, "portal_account", "mpi_id", "portal_account_id")

        appointment_rows: list[tuple[Any, ...]] = []
        appointment_status_rows: list[tuple[Any, ...]] = []
        appointment_context: dict[str, tuple[PatientSeed, str, datetime]] = {}
        status_cycle = ("FULFILLED", "FULFILLED", "FULFILLED", "CANCELLED", "NOSHOW", "BOOKED")

        for patient in account_patients:
            for local_index in range(1, 3 + patient.sequence % 3):
                appointment_number = f"APT-GEN-{patient.sequence:06d}-{local_index:02d}"
                scheduled_day = date(2024, 1, 2) + timedelta(
                    days=(patient.sequence * 13 + local_index * 47) % 820
                )
                scheduled_at = _at(
                    scheduled_day, 8 + (patient.sequence + local_index) % 8, (local_index * 10) % 60
                )
                status = status_cycle[(patient.sequence + local_index) % len(status_cycle)]
                encounter_candidates = emr_result.encounter_numbers[patient.mpi_id]
                external_encounter = (
                    encounter_candidates[min(local_index - 1, len(encounter_candidates) - 1)]
                    if status == "FULFILLED"
                    else None
                )
                appointment_rows.append(
                    (
                        appointment_number,
                        account_ids[patient.mpi_id],
                        patient.mpi_id,
                        "CLINICAL_SERVICE",
                        "GENERAL_OUTPATIENT",
                        "普通门诊",
                        "ONCOLOGY" if patient.sequence % 4 == 0 else "RESPIRATORY",
                        "肿瘤内科" if patient.sequence % 4 == 0 else "呼吸内科",
                        None,
                        f"演示医师{patient.sequence % 18 + 1:02d}",
                        scheduled_at,
                        scheduled_at + timedelta(minutes=30),
                        status,
                        "ACCEPTED" if status not in {"CANCELLED", "NOSHOW"} else "DECLINED",
                        ("APP", "WECHAT", "WEB", "CALL_CENTER")[patient.sequence % 4],
                        "FOLLOW_UP",
                        "复诊预约",
                        (
                            "患者行程变化"
                            if status == "CANCELLED"
                            else "患者未到诊" if status == "NOSHOW" else None
                        ),
                        external_encounter,
                        None,
                        scheduled_at - timedelta(days=7),
                        scheduled_at - timedelta(hours=2),
                    )
                )
                appointment_context[appointment_number] = (patient, status, scheduled_at)

            if patient.oncology:
                oncology = patient.oncology
                consult_number = f"APT-RTCONS-{patient.sequence:06d}"
                consult_at = _at(oncology.consult_date, 9 + patient.sequence % 6)
                appointment_rows.append(
                    (
                        consult_number,
                        account_ids[patient.mpi_id],
                        patient.mpi_id,
                        "RADIOTHERAPY",
                        "RT_CONSULT",
                        "放射治疗门诊评估",
                        "RADIATION_ONCOLOGY",
                        "放射治疗科",
                        None,
                        f"演示放疗医师{patient.sequence % 4 + 1}",
                        consult_at,
                        consult_at + timedelta(minutes=45),
                        "FULFILLED",
                        "ACCEPTED",
                        "APP",
                        oncology.diagnosis_code,
                        oncology.diagnosis_name,
                        None,
                        emr_result.oncology_encounters[patient.mpi_id],
                        oncology.course_uid,
                        consult_at - timedelta(days=5),
                        consult_at + timedelta(minutes=50),
                    )
                )
                appointment_context[consult_number] = (patient, "FULFILLED", consult_at)

                delivered_count = _course_delivery_count(oncology)
                anomaly_fraction = (
                    2 if patient.sequence in {3, 17, 42} and delivered_count >= 2 else None
                )
                missed_fraction = (
                    4
                    if patient.sequence % 11 == 0
                    and delivered_count >= 5
                    and oncology.course_status != "COMPLETED"
                    else None
                )
                for fraction_number in range(1, oncology.fraction_count + 1):
                    scheduled_day = _add_weekdays(oncology.planned_start_date, fraction_number - 1)
                    scheduled_at = _at(
                        scheduled_day, 8 + patient.sequence % 8, (fraction_number % 4) * 10
                    )
                    if fraction_number == anomaly_fraction:
                        status = "CANCELLED"
                    elif fraction_number == missed_fraction:
                        status = "NOSHOW"
                    elif fraction_number <= delivered_count:
                        status = "FULFILLED"
                    elif oncology.course_status == "DISCONTINUED":
                        status = "CANCELLED"
                    else:
                        status = "BOOKED"
                    appointment_number = f"APT-RT-{patient.sequence:06d}-{fraction_number:02d}"
                    appointment_rows.append(
                        (
                            appointment_number,
                            account_ids[patient.mpi_id],
                            patient.mpi_id,
                            "RADIOTHERAPY",
                            "RT_FRACTION",
                            "放射治疗分次",
                            "RADIATION_ONCOLOGY",
                            "放射治疗科",
                            None,
                            f"演示放疗团队{patient.sequence % 3 + 1}",
                            scheduled_at,
                            scheduled_at + timedelta(minutes=30),
                            status,
                            "DECLINED" if status in {"CANCELLED", "NOSHOW"} else "ACCEPTED",
                            "APP",
                            oncology.site_code,
                            f"{oncology.site_name}第{fraction_number}次治疗",
                            (
                                "用于跨系统对账的模拟取消场景"
                                if fraction_number == anomaly_fraction
                                else (
                                    "患者未到诊"
                                    if fraction_number == missed_fraction
                                    else "疗程终止，后续预约取消" if status == "CANCELLED" else None
                                )
                            ),
                            None,
                            oncology.course_uid,
                            consult_at,
                            scheduled_at - timedelta(minutes=15),
                        )
                    )
                    appointment_context[appointment_number] = (patient, status, scheduled_at)

        _insert_many(
            connection,
            "appointment",
            (
                "appointment_number",
                "portal_account_id",
                "mpi_id",
                "service_category",
                "service_code",
                "service_name",
                "department_code",
                "department_name",
                "practitioner_no",
                "practitioner_name",
                "scheduled_start_at",
                "scheduled_end_at",
                "appointment_status",
                "participant_status",
                "booking_channel",
                "reason_code",
                "reason_text",
                "cancellation_reason",
                "external_emr_encounter_number",
                "external_course_uid",
                "created_at",
                "updated_at",
            ),
            appointment_rows,
        )
        appointment_ids = _fetch_map(
            connection, "appointment", "appointment_number", "appointment_id"
        )
        for appointment_number, (_patient, status, scheduled_at) in appointment_context.items():
            appointment_status_rows.append(
                (
                    appointment_ids[appointment_number],
                    None,
                    "PENDING",
                    scheduled_at - timedelta(days=7),
                    "PATIENT",
                    "患者提交预约",
                )
            )
            appointment_status_rows.append(
                (
                    appointment_ids[appointment_number],
                    "PENDING",
                    status,
                    (
                        scheduled_at - timedelta(minutes=15)
                        if status in {"ARRIVED", "FULFILLED", "NOSHOW"}
                        else scheduled_at - timedelta(days=2)
                    ),
                    (
                        "EXTERNAL_SYSTEM"
                        if status == "FULFILLED"
                        else "PATIENT" if status == "CANCELLED" else "SYSTEM"
                    ),
                    "EMR/RVS履约回写" if status == "FULFILLED" else "预约状态更新",
                )
            )
        _insert_many(
            connection,
            "appointment_status_history",
            (
                "appointment_id",
                "from_status",
                "to_status",
                "changed_at",
                "changed_by_type",
                "change_reason",
            ),
            appointment_status_rows,
        )

        questionnaire_rows = [
            ("PREVISIT-V1", "就诊前健康信息", "1.0", "PRE_VISIT", date(2024, 1, 1), None, True),
            (
                "RT-PRO-CTCAE-V1",
                "放疗患者报告症状评估",
                "1.0",
                "PATIENT_REPORTED_OUTCOME",
                date(2024, 1, 1),
                None,
                True,
            ),
            ("VISIT-SAT-V1", "就诊满意度", "1.0", "SATISFACTION", date(2024, 1, 1), None, True),
        ]
        _insert_many(
            connection,
            "questionnaire",
            (
                "questionnaire_code",
                "questionnaire_name",
                "questionnaire_version",
                "questionnaire_purpose",
                "active_from",
                "active_to",
                "active",
            ),
            questionnaire_rows,
        )
        questionnaire_ids = _fetch_map(
            connection, "questionnaire", "questionnaire_code", "questionnaire_id"
        )
        questionnaire_item_rows = [
            (
                questionnaire_ids["PREVISIT-V1"],
                "FEVER",
                "过去24小时是否发热？",
                "BOOLEAN",
                None,
                1,
                True,
            ),
            (
                questionnaire_ids["PREVISIT-V1"],
                "PAIN_SCORE",
                "当前疼痛评分（0-10）",
                "INTEGER",
                "score",
                2,
                True,
            ),
            (
                questionnaire_ids["PREVISIT-V1"],
                "MED_CHANGE",
                "近期用药是否变化？",
                "BOOLEAN",
                None,
                3,
                True,
            ),
            (
                questionnaire_ids["RT-PRO-CTCAE-V1"],
                "FATIGUE",
                "疲乏程度（0-4）",
                "INTEGER",
                "grade",
                1,
                True,
            ),
            (
                questionnaire_ids["RT-PRO-CTCAE-V1"],
                "NAUSEA",
                "恶心程度（0-4）",
                "INTEGER",
                "grade",
                2,
                True,
            ),
            (
                questionnaire_ids["RT-PRO-CTCAE-V1"],
                "PAIN",
                "疼痛程度（0-4）",
                "INTEGER",
                "grade",
                3,
                True,
            ),
            (
                questionnaire_ids["RT-PRO-CTCAE-V1"],
                "SKIN",
                "照射区皮肤反应（0-4）",
                "INTEGER",
                "grade",
                4,
                True,
            ),
            (
                questionnaire_ids["RT-PRO-CTCAE-V1"],
                "DYSPHAGIA",
                "吞咽困难程度（0-4）",
                "INTEGER",
                "grade",
                5,
                True,
            ),
            (
                questionnaire_ids["RT-PRO-CTCAE-V1"],
                "APPETITE",
                "食欲下降程度（0-4）",
                "INTEGER",
                "grade",
                6,
                True,
            ),
            (
                questionnaire_ids["VISIT-SAT-V1"],
                "OVERALL",
                "本次服务总体评分（1-5）",
                "INTEGER",
                "score",
                1,
                True,
            ),
        ]
        _insert_many(
            connection,
            "questionnaire_item",
            (
                "questionnaire_id",
                "item_code",
                "item_text",
                "answer_type",
                "unit",
                "display_order",
                "required",
            ),
            questionnaire_item_rows,
        )
        item_ids = _fetch_map(
            connection, "questionnaire_item", "item_code", "questionnaire_item_id"
        )

        response_rows: list[tuple[Any, ...]] = []
        response_specs: list[
            tuple[str, str, PatientSeed, int, str | None, datetime, list[tuple[str, float]]]
        ] = []
        response_sequence = 1
        for patient in account_patients:
            if patient.sequence % 3 == 0:
                appointment_number = f"APT-GEN-{patient.sequence:06d}-01"
                authored = appointment_context[appointment_number][2] - timedelta(days=1)
                answers = [
                    ("FEVER", float(patient.sequence % 11 == 0)),
                    ("PAIN_SCORE", float(patient.sequence % 8)),
                    ("MED_CHANGE", float(patient.sequence % 5 == 0)),
                ]
                response_number = f"QRESP-{response_sequence:08d}"
                response_rows.append(
                    (
                        response_number,
                        questionnaire_ids["PREVISIT-V1"],
                        account_ids[patient.mpi_id],
                        patient.mpi_id,
                        appointment_ids[appointment_number],
                        None,
                        "COMPLETED",
                        authored,
                        authored + timedelta(minutes=5),
                        sum(value for _, value in answers),
                        "MEDIUM" if patient.sequence % 11 == 0 else "LOW",
                    )
                )
                response_specs.append(
                    (
                        response_number,
                        "PREVISIT-V1",
                        patient,
                        appointment_ids[appointment_number],
                        None,
                        authored,
                        answers,
                    )
                )
                response_sequence += 1

            if patient.oncology:
                oncology = patient.oncology
                delivered_count = _course_delivery_count(oncology)
                for fraction_number in range(1, delivered_count + 1, 5):
                    authored_day = _add_weekdays(oncology.planned_start_date, fraction_number - 1)
                    authored = _at(authored_day, 18)
                    progress = fraction_number / max(oncology.fraction_count, 1)
                    base_grade = min(
                        3, int(progress * 4) + (1 if patient.sequence % 13 == 0 else 0)
                    )
                    answers = [
                        ("FATIGUE", float(base_grade)),
                        ("NAUSEA", float(max(0, base_grade - 1))),
                        ("PAIN", float(patient.sequence % 3)),
                        (
                            "SKIN",
                            float(
                                base_grade
                                if oncology.site_code in {"BREAST", "NASOPHARYNX"}
                                else max(0, base_grade - 1)
                            ),
                        ),
                        (
                            "DYSPHAGIA",
                            float(
                                base_grade
                                if oncology.site_code in {"NASOPHARYNX", "ESOPHAGUS"}
                                else 0
                            ),
                        ),
                        ("APPETITE", float(max(0, base_grade - 1))),
                    ]
                    total_score = sum(value for _, value in answers)
                    risk = (
                        "HIGH"
                        if max(value for _, value in answers) >= 3
                        else "MEDIUM" if total_score >= 6 else "LOW"
                    )
                    appointment_number = f"APT-RT-{patient.sequence:06d}-{fraction_number:02d}"
                    response_number = f"QRESP-{response_sequence:08d}"
                    response_rows.append(
                        (
                            response_number,
                            questionnaire_ids["RT-PRO-CTCAE-V1"],
                            account_ids[patient.mpi_id],
                            patient.mpi_id,
                            appointment_ids[appointment_number],
                            oncology.course_uid,
                            "COMPLETED",
                            authored,
                            authored + timedelta(minutes=4),
                            total_score,
                            risk,
                        )
                    )
                    response_specs.append(
                        (
                            response_number,
                            "RT-PRO-CTCAE-V1",
                            patient,
                            appointment_ids[appointment_number],
                            oncology.course_uid,
                            authored,
                            answers,
                        )
                    )
                    response_sequence += 1
        _insert_many(
            connection,
            "questionnaire_response",
            (
                "response_number",
                "questionnaire_id",
                "portal_account_id",
                "mpi_id",
                "appointment_id",
                "external_course_uid",
                "response_status",
                "authored_at",
                "submitted_at",
                "total_score",
                "risk_level",
            ),
            response_rows,
        )
        response_ids = _fetch_map(
            connection, "questionnaire_response", "response_number", "questionnaire_response_id"
        )
        answer_rows: list[tuple[Any, ...]] = []
        for (
            response_number,
            _questionnaire_code,
            _patient,
            _appointment_id,
            _course_uid,
            _authored,
            answers,
        ) in response_specs:
            for item_code, numeric_value in answers:
                if item_code in {"FEVER", "MED_CHANGE"}:
                    answer_rows.append(
                        (
                            response_ids[response_number],
                            item_ids[item_code],
                            bool(numeric_value),
                            None,
                            None,
                            None,
                        )
                    )
                else:
                    answer_rows.append(
                        (
                            response_ids[response_number],
                            item_ids[item_code],
                            None,
                            numeric_value,
                            None,
                            None,
                        )
                    )
        _insert_many(
            connection,
            "questionnaire_answer",
            (
                "questionnaire_response_id",
                "questionnaire_item_id",
                "value_boolean",
                "value_numeric",
                "value_code",
                "value_text",
            ),
            answer_rows,
        )

        consent_rows: list[tuple[Any, ...]] = []
        consent_sequence = 1
        for patient in account_patients:
            effective = patient.registered_at + timedelta(days=2)
            consent_rows.append(
                (
                    f"CONSENT-{consent_sequence:08d}",
                    account_ids[patient.mpi_id],
                    patient.mpi_id,
                    "PORTAL_SERVICE",
                    "2026.1",
                    "ACTIVE",
                    "PERMIT",
                    effective,
                    None,
                    effective,
                    "APP_SMS_OTP",
                    None,
                )
            )
            consent_sequence += 1
            if patient.oncology:
                consent_rows.append(
                    (
                        f"CONSENT-{consent_sequence:08d}",
                        account_ids[patient.mpi_id],
                        patient.mpi_id,
                        "RADIOTHERAPY",
                        "RT-2026.2",
                        "ACTIVE",
                        "PERMIT",
                        _at(patient.oncology.consult_date, 11),
                        None,
                        _at(patient.oncology.consult_date, 11),
                        "APP_E_SIGNATURE",
                        patient.oncology.course_uid,
                    )
                )
                consent_sequence += 1
        _insert_many(
            connection,
            "consent_record",
            (
                "consent_number",
                "portal_account_id",
                "mpi_id",
                "consent_scope",
                "policy_version",
                "consent_status",
                "decision",
                "effective_from",
                "effective_to",
                "signed_at",
                "signature_method",
                "external_course_uid",
            ),
            consent_rows,
        )

        thread_rows: list[tuple[Any, ...]] = []
        message_rows_by_thread: dict[str, list[tuple[Any, ...]]] = {}
        for patient in account_patients[:ONCOLOGY_PATIENT_COUNT]:
            oncology = patient.oncology
            assert oncology is not None
            thread_number = f"THREAD-RT-{patient.sequence:06d}"
            opened_at = _at(oncology.planned_start_date, 17)
            thread_rows.append(
                (
                    thread_number,
                    account_ids[patient.mpi_id],
                    patient.mpi_id,
                    "RADIOTHERAPY",
                    oncology.course_uid,
                    "RESOLVED" if oncology.course_status == "COMPLETED" else "OPEN",
                    opened_at,
                    (
                        opened_at + timedelta(days=3)
                        if oncology.course_status == "COMPLETED"
                        else None
                    ),
                )
            )
            message_rows_by_thread[thread_number] = [
                (
                    "PATIENT",
                    patient.name,
                    opened_at,
                    opened_at + timedelta(minutes=8),
                    "SYMPTOM",
                    "请问治疗期间出现轻度疲乏是否需要提前就诊？",
                    False,
                ),
                (
                    "CARE_TEAM",
                    "演示放疗护理团队",
                    opened_at + timedelta(minutes=25),
                    opened_at + timedelta(minutes=40),
                    "CARE_ADVICE",
                    "建议记录症状评分，若达到3级或伴发热请及时联系。",
                    False,
                ),
                (
                    "SYSTEM",
                    "患者端系统",
                    opened_at + timedelta(days=1),
                    opened_at + timedelta(days=1, minutes=3),
                    "REMINDER",
                    "请完成今日放疗症状评估问卷。",
                    False,
                ),
            ]
        _insert_many(
            connection,
            "message_thread",
            (
                "thread_number",
                "portal_account_id",
                "mpi_id",
                "thread_topic",
                "external_course_uid",
                "thread_status",
                "opened_at",
                "closed_at",
            ),
            thread_rows,
        )
        thread_ids = _fetch_map(connection, "message_thread", "thread_number", "message_thread_id")
        secure_message_rows = [
            (thread_ids[thread_number], *message)
            for thread_number, messages in message_rows_by_thread.items()
            for message in messages
        ]
        _insert_many(
            connection,
            "secure_message",
            (
                "message_thread_id",
                "sender_type",
                "sender_display",
                "sent_at",
                "read_at",
                "message_category",
                "message_text",
                "urgent",
            ),
            secure_message_rows,
        )

        bill_rows: list[tuple[Any, ...]] = []
        for patient in account_patients:
            issued = datetime(2026, 1, 5, 10) + timedelta(days=patient.sequence % 180)
            gross = round(180 + (patient.sequence % 17) * 23.5, 2)
            insurance = round(gross * (0.65 if patient.insurance_type != "SELF_PAY" else 0), 2)
            patient_amount = round(gross - insurance, 2)
            paid = patient.sequence % 7 != 0
            bill_rows.append(
                (
                    f"BILL-GEN-{patient.sequence:06d}",
                    account_ids[patient.mpi_id],
                    patient.mpi_id,
                    emr_result.encounter_numbers[patient.mpi_id][0],
                    None,
                    "OUTPATIENT",
                    issued,
                    issued + timedelta(days=30),
                    gross,
                    insurance,
                    patient_amount,
                    0 if paid else patient_amount,
                    "PAID" if paid else "OPEN",
                )
            )
            if patient.oncology:
                oncology_gross = round(12000 + (patient.sequence % 9) * 1850.0, 2)
                oncology_insurance = round(
                    oncology_gross * (0.72 if patient.insurance_type != "SELF_PAY" else 0), 2
                )
                oncology_patient = round(oncology_gross - oncology_insurance, 2)
                oncology_paid = patient.sequence % 8 != 0
                bill_rows.append(
                    (
                        f"BILL-RT-{patient.sequence:06d}",
                        account_ids[patient.mpi_id],
                        patient.mpi_id,
                        emr_result.oncology_encounters[patient.mpi_id],
                        patient.oncology.course_uid,
                        "RADIOTHERAPY",
                        _at(patient.oncology.planned_start_date, 12),
                        _at(patient.oncology.planned_start_date, 12) + timedelta(days=45),
                        oncology_gross,
                        oncology_insurance,
                        oncology_patient,
                        0 if oncology_paid else oncology_patient,
                        "PAID" if oncology_paid else "OPEN",
                    )
                )
        _insert_many(
            connection,
            "bill",
            (
                "bill_number",
                "portal_account_id",
                "mpi_id",
                "external_emr_encounter_number",
                "external_course_uid",
                "bill_type",
                "issued_at",
                "due_at",
                "gross_amount",
                "insurance_amount",
                "patient_amount",
                "outstanding_amount",
                "bill_status",
            ),
            bill_rows,
        )
        bill_ids = _fetch_map(connection, "bill", "bill_number", "bill_id")
        payment_rows: list[tuple[Any, ...]] = []
        payment_sequence = 1
        for _bill_number, bill_id in bill_ids.items():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT patient_amount, issued_at, bill_status FROM bill WHERE bill_id = %s",
                    (bill_id,),
                )
                amount, issued_at, bill_status = cursor.fetchone()
            if bill_status == "PAID":
                payment_rows.append(
                    (
                        f"PAY-DEMO-{payment_sequence:08d}",
                        bill_id,
                        "PAYMENT",
                        ("WECHAT_PAY", "ALIPAY", "BANK_CARD")[payment_sequence % 3],
                        "APP",
                        amount,
                        "SUCCEEDED",
                        issued_at + timedelta(minutes=15),
                        issued_at + timedelta(minutes=16),
                        f"PROVIDER-DEMO-{payment_sequence:08d}",
                    )
                )
                payment_sequence += 1
        _insert_many(
            connection,
            "payment_transaction",
            (
                "transaction_number",
                "bill_id",
                "transaction_type",
                "payment_method",
                "payment_channel",
                "amount",
                "transaction_status",
                "requested_at",
                "completed_at",
                "provider_reference",
            ),
            payment_rows,
        )

        notification_rows: list[tuple[Any, ...]] = []
        notification_sequence = 1
        for appointment_number, (patient, status, scheduled_at) in appointment_context.items():
            notification_rows.append(
                (
                    account_ids[patient.mpi_id],
                    patient.mpi_id,
                    (
                        "RADIOTHERAPY_REMINDER"
                        if appointment_number.startswith("APT-RT-")
                        else "APPOINTMENT_REMINDER"
                    ),
                    ("APP_PUSH", "SMS", "WECHAT")[patient.sequence % 3],
                    scheduled_at - timedelta(days=1),
                    scheduled_at - timedelta(days=1) if status not in {"CANCELLED"} else None,
                    "CANCELLED" if status == "CANCELLED" else "DELIVERED",
                    "APPOINTMENT",
                    appointment_number,
                    "就诊提醒",
                    f"您预约的{appointment_number}将于{scheduled_at:%Y-%m-%d %H:%M}开始。",
                )
            )
            notification_sequence += 1
        _insert_many(
            connection,
            "notification",
            (
                "portal_account_id",
                "mpi_id",
                "notification_type",
                "delivery_channel",
                "scheduled_at",
                "delivered_at",
                "delivery_status",
                "reference_type",
                "reference_number",
                "title",
                "content_text",
            ),
            notification_rows,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def seed_rvs(patients: list[PatientSeed]) -> None:
    rng = random.Random(RANDOM_SEED + 3)
    connection = _admin_connection("rvs_demo")
    try:
        oncology_patients = patients[:ONCOLOGY_PATIENT_COUNT]
        _insert_many(
            connection,
            "rt_patient",
            (
                "rvs_patient_number",
                "mpi_id",
                "emr_medical_record_number",
                "patient_name",
                "gender_code",
                "birth_date",
                "registered_at",
                "patient_status",
                "synthetic_identity",
            ),
            [
                (
                    f"RVP-{patient.sequence:06d}",
                    patient.mpi_id,
                    patient.mrn,
                    patient.name,
                    patient.gender,
                    patient.birth_date,
                    _at(patient.oncology.consult_date, 8),
                    "ACTIVE",
                    True,
                )
                for patient in oncology_patients
                if patient.oncology is not None
            ],
        )
        patient_ids = _fetch_map(connection, "rt_patient", "mpi_id", "rt_patient_id")
        _insert_many(
            connection,
            "treatment_machine",
            (
                "machine_code",
                "machine_name",
                "manufacturer",
                "model_name",
                "machine_type",
                "supported_energies",
                "commissioned_date",
                "active",
            ),
            [
                (
                    "LINAC-A",
                    "直线加速器A",
                    "Varian",
                    "TrueBeam",
                    "LINAC",
                    "6X,10X,6FFF,10FFF",
                    date(2021, 5, 12),
                    True,
                ),
                (
                    "LINAC-B",
                    "直线加速器B",
                    "Elekta",
                    "Versa HD",
                    "LINAC",
                    "6X,10X,6FFF",
                    date(2022, 9, 8),
                    True,
                ),
                (
                    "TOMO-1",
                    "螺旋断层放疗机",
                    "Accuray",
                    "Radixact",
                    "TOMOTHERAPY",
                    "6MV",
                    date(2023, 4, 18),
                    True,
                ),
                (
                    "CK-1",
                    "射波刀",
                    "Accuray",
                    "CyberKnife S7",
                    "CYBERKNIFE",
                    "6MV",
                    date(2024, 2, 20),
                    True,
                ),
            ],
        )
        machine_ids = _fetch_map(
            connection, "treatment_machine", "machine_code", "treatment_machine_id"
        )

        for patient in oncology_patients:
            oncology = patient.oncology
            assert oncology is not None
            delivered_target = _course_delivery_count(oncology)
            physician_no = f"DOC-{5 + patient.sequence % 4:04d}"
            physician_name = f"演示放疗医师{patient.sequence % 4 + 1}"
            simulation_date = oncology.consult_date + timedelta(days=7)
            delivered_schedule = [
                _add_weekdays(oncology.planned_start_date, index)
                for index in range(oncology.fraction_count)
            ]
            actual_end = delivered_schedule[delivered_target - 1] if delivered_target else None
            if oncology.course_status not in {"COMPLETED", "DISCONTINUED"}:
                actual_end = None

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO treatment_course (
                        course_uid, course_number, rt_patient_id, mpi_id, source_request_number,
                        diagnosis_code, diagnosis_name, treatment_site_code, treatment_site_name,
                        laterality, clinical_stage, treatment_intent, attending_oncologist_no,
                        attending_oncologist_name, consult_date, simulation_date, planned_start_date,
                        actual_start_date, actual_end_date, course_status, discontinuation_reason,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) RETURNING treatment_course_id
                    """,
                    (
                        oncology.course_uid,
                        f"COURSE-{patient.sequence:06d}",
                        patient_ids[patient.mpi_id],
                        patient.mpi_id,
                        oncology.request_number,
                        oncology.diagnosis_code,
                        oncology.diagnosis_name,
                        oncology.site_code,
                        oncology.site_name,
                        oncology.laterality,
                        oncology.stage,
                        oncology.intent,
                        physician_no,
                        physician_name,
                        oncology.consult_date,
                        simulation_date,
                        oncology.planned_start_date,
                        oncology.planned_start_date if delivered_target else None,
                        actual_end,
                        oncology.course_status,
                        (
                            "患者一般状况下降，经MDT讨论终止放疗"
                            if oncology.course_status == "DISCONTINUED"
                            else None
                        ),
                        _at(oncology.consult_date, 11),
                        datetime(2026, 8, 29, 12),
                    ),
                )
                course_id = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    INSERT INTO prescription (
                        prescription_number, treatment_course_id, prescribed_total_dose_gy,
                        prescribed_fraction_count, dose_per_fraction_gy, fractions_per_day,
                        treatment_days_per_week, radiation_type, technique, image_guidance_protocol,
                        prescription_status, prescribed_at, prescribed_by_no, prescribed_by_name
                    ) VALUES (%s, %s, %s, %s, %s, 1, 5, 'PHOTON', %s, %s, %s, %s, %s, %s)
                    RETURNING prescription_id
                    """,
                    (
                        f"RX-{patient.sequence:06d}",
                        course_id,
                        oncology.total_dose_gy,
                        oncology.fraction_count,
                        oncology.dose_per_fraction_gy,
                        oncology.technique,
                        oncology.image_guidance,
                        (
                            "COMPLETED"
                            if oncology.course_status == "COMPLETED"
                            else (
                                "DISCONTINUED"
                                if oncology.course_status == "DISCONTINUED"
                                else "ACTIVE"
                            )
                        ),
                        _at(oncology.consult_date + timedelta(days=1), 10),
                        physician_no,
                        physician_name,
                    ),
                )
                prescription_id = int(cursor.fetchone()[0])
                plan_uid = f"1.2.826.0.1.3680043.10.999.2.{patient.sequence}"
                sop_uid = f"1.2.826.0.1.3680043.10.999.3.{patient.sequence}"
                cursor.execute(
                    """
                    INSERT INTO rt_plan (
                        plan_uid, sop_instance_uid, treatment_course_id, prescription_id, plan_label,
                        plan_name, plan_version, plan_status, treatment_technique, planned_total_dose_gy,
                        planned_fraction_count, dose_calculation_algorithm, planning_system,
                        planning_system_version, created_at, approved_at, approved_by_no,
                        approved_by_name, is_current
                    ) VALUES (%s, %s, %s, %s, %s, %s, 1, 'APPROVED', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    RETURNING rt_plan_id
                    """,
                    (
                        plan_uid,
                        sop_uid,
                        course_id,
                        prescription_id,
                        f"PLAN{patient.sequence:04d}",
                        f"{oncology.site_name}-{oncology.technique}",
                        oncology.technique,
                        oncology.total_dose_gy,
                        oncology.fraction_count,
                        "Acuros XB" if oncology.technique in {"VMAT", "IMRT"} else "AAA",
                        "Eclipse",
                        "18.1",
                        _at(simulation_date + timedelta(days=2), 14),
                        _at(simulation_date + timedelta(days=8), 16),
                        "PHYS-DEMO-01",
                        "演示物理师01",
                    ),
                )
                plan_id = int(cursor.fetchone()[0])
                beam_count = (
                    2 if oncology.technique == "VMAT" else 5 if oncology.technique == "IMRT" else 3
                )
                cursor.execute(
                    """
                    INSERT INTO fraction_group (
                        rt_plan_id, fraction_group_number, fraction_pattern,
                        number_of_fractions_planned, number_of_beams, dose_per_fraction_gy
                    ) VALUES (%s, 1, 'MON-FRI', %s, %s, %s)
                    RETURNING fraction_group_id
                    """,
                    (plan_id, oncology.fraction_count, beam_count, oncology.dose_per_fraction_gy),
                )
                fraction_group_id = int(cursor.fetchone()[0])

            beam_rows: list[tuple[Any, ...]] = []
            for beam_number in range(1, beam_count + 1):
                beam_type = (
                    "ARC"
                    if oncology.technique == "VMAT"
                    else "DYNAMIC" if oncology.technique in {"IMRT", "SBRT"} else "STATIC"
                )
                planned_mu = round(180 + (patient.sequence % 17) * 4.2 + beam_number * 22.5, 3)
                beam_rows.append(
                    (
                        plan_id,
                        fraction_group_id,
                        beam_number,
                        f"B{beam_number:02d}",
                        beam_type,
                        "PHOTON",
                        6.0 if oncology.technique != "SBRT" else 10.0,
                        (
                            None
                            if beam_type == "ARC"
                            else float((beam_number - 1) * (360 / beam_count))
                        ),
                        float((beam_number * 7) % 90),
                        0.0,
                        planned_mu,
                        600 if oncology.technique != "SBRT" else 1200,
                        178 if beam_type == "ARC" else 40 if beam_type == "DYNAMIC" else 2,
                    )
                )
            _insert_many(
                connection,
                "beam",
                (
                    "rt_plan_id",
                    "fraction_group_id",
                    "beam_number",
                    "beam_name",
                    "beam_type",
                    "radiation_type",
                    "nominal_energy_mev",
                    "gantry_angle_deg",
                    "collimator_angle_deg",
                    "couch_angle_deg",
                    "planned_meterset_mu",
                    "monitor_unit_rate",
                    "control_point_count",
                ),
                beam_rows,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT beam_id, beam_number, planned_meterset_mu FROM beam WHERE rt_plan_id = %s ORDER BY beam_number",
                    (plan_id,),
                )
                beams = [(int(row[0]), int(row[1]), float(row[2])) for row in cursor.fetchall()]

            machine_code = (
                "CK-1"
                if oncology.technique in {"SBRT", "SRS"}
                else ("LINAC-A", "LINAC-B", "TOMO-1")[patient.sequence % 3]
            )
            missed_fraction = (
                4
                if patient.sequence % 11 == 0
                and delivered_target >= 5
                and oncology.course_status != "COMPLETED"
                else None
            )
            partial_fraction = (
                delivered_target
                if oncology.course_status == "ON_HOLD" and patient.sequence % 2 == 0
                else None
            )
            fraction_rows: list[tuple[Any, ...]] = []
            fraction_status_by_number: dict[int, str] = {}
            delivered_dose_by_number: dict[int, float] = {}
            for fraction_number, scheduled_day in enumerate(delivered_schedule, start=1):
                scheduled = _at(scheduled_day, 8 + patient.sequence % 8, (fraction_number % 4) * 10)
                if fraction_number == missed_fraction:
                    status = "MISSED"
                    delivered_dose = 0.0
                elif fraction_number == partial_fraction:
                    status = "PARTIALLY_DELIVERED"
                    delivered_dose = round(oncology.dose_per_fraction_gy * 0.5, 3)
                elif fraction_number <= delivered_target:
                    status = "DELIVERED"
                    delivered_dose = oncology.dose_per_fraction_gy
                elif oncology.course_status == "DISCONTINUED":
                    status = "NOT_DELIVERED"
                    delivered_dose = 0.0
                else:
                    status = "SCHEDULED"
                    delivered_dose = 0.0
                actual_start = (
                    scheduled + timedelta(minutes=(patient.sequence + fraction_number) % 12)
                    if delivered_dose > 0
                    else None
                )
                actual_end_time = (
                    actual_start + timedelta(minutes=18 + beam_count * 3) if actual_start else None
                )
                fraction_rows.append(
                    (
                        f"1.2.826.0.1.3680043.10.999.4.{patient.sequence}.{fraction_number}",
                        course_id,
                        plan_id,
                        fraction_group_id,
                        fraction_number,
                        fraction_number,
                        scheduled,
                        actual_start,
                        actual_end_time,
                        status,
                        machine_ids[machine_code],
                        oncology.dose_per_fraction_gy,
                        delivered_dose,
                        "仰卧位，热塑膜/体膜固定，影像引导后治疗",
                        "演示技师A",
                        "演示技师B",
                        physician_name if fraction_number == 1 else "演示审核技师",
                    )
                )
                fraction_status_by_number[fraction_number] = status
                delivered_dose_by_number[fraction_number] = delivered_dose
            _insert_many(
                connection,
                "treatment_fraction",
                (
                    "treatment_session_uid",
                    "treatment_course_id",
                    "rt_plan_id",
                    "fraction_group_id",
                    "fraction_number",
                    "clinical_fraction_number",
                    "scheduled_start_at",
                    "actual_start_at",
                    "actual_end_at",
                    "fraction_status",
                    "treatment_machine_id",
                    "planned_dose_gy",
                    "delivered_dose_gy",
                    "setup_note",
                    "therapist_1",
                    "therapist_2",
                    "verified_by",
                ),
                fraction_rows,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT treatment_fraction_id, fraction_number, actual_start_at, actual_end_at "
                    "FROM treatment_fraction WHERE treatment_course_id = %s ORDER BY fraction_number",
                    (course_id,),
                )
                fraction_records = {
                    int(number): (int(fraction_id), actual_start, actual_end_time)
                    for fraction_id, number, actual_start, actual_end_time in cursor.fetchall()
                }

            delivery_rows: list[tuple[Any, ...]] = []
            imaging_rows: list[tuple[Any, ...]] = []
            for fraction_number, status in fraction_status_by_number.items():
                if status not in {"DELIVERED", "PARTIALLY_DELIVERED"}:
                    continue
                fraction_id, actual_start, actual_end_time = fraction_records[fraction_number]
                assert actual_start is not None
                for beam_id, beam_number, planned_mu in beams:
                    if status == "PARTIALLY_DELIVERED":
                        delivered_mu = round(planned_mu * 0.5, 3)
                        termination = "PARTIAL"
                        reason = "患者不适，完成当前控制点后暂停"
                    elif (patient.sequence + fraction_number + beam_number) % 47 == 0:
                        first_part = round(planned_mu * 0.42, 3)
                        second_part = round(planned_mu - first_part, 3)
                        delivery_rows.append(
                            (
                                fraction_id,
                                beam_id,
                                1,
                                planned_mu,
                                first_part,
                                actual_start,
                                actual_start + timedelta(minutes=2),
                                "INTERRUPTED",
                                "门联锁触发后检查并恢复",
                                f"1.2.826.0.1.3680043.10.999.5.{patient.sequence}.{fraction_number}.{beam_number}.1",
                            )
                        )
                        delivery_rows.append(
                            (
                                fraction_id,
                                beam_id,
                                2,
                                planned_mu,
                                second_part,
                                actual_start + timedelta(minutes=5),
                                actual_end_time,
                                "NORMAL",
                                None,
                                f"1.2.826.0.1.3680043.10.999.5.{patient.sequence}.{fraction_number}.{beam_number}.2",
                            )
                        )
                        continue
                    else:
                        delivered_mu = round(planned_mu * (0.995 + rng.random() * 0.01), 3)
                        termination = "NORMAL"
                        reason = None
                    delivery_rows.append(
                        (
                            fraction_id,
                            beam_id,
                            1,
                            planned_mu,
                            delivered_mu,
                            actual_start,
                            actual_end_time,
                            termination,
                            reason,
                            f"1.2.826.0.1.3680043.10.999.5.{patient.sequence}.{fraction_number}.{beam_number}.1",
                        )
                    )

                if (
                    fraction_number == 1
                    or fraction_number % 5 == 0
                    or oncology.image_guidance == "DAILY_CBCT"
                ):
                    imaging_rows.append(
                        (
                            fraction_id,
                            "CBCT" if "CBCT" in oncology.image_guidance else "KV_PAIR",
                            actual_start - timedelta(minutes=8),
                            "BONE_AND_SOFT_TISSUE",
                            round(rng.uniform(-4.5, 4.5), 2),
                            round(rng.uniform(-5.0, 5.0), 2),
                            round(rng.uniform(-3.5, 3.5), 2),
                            round(rng.uniform(-1.0, 1.0), 2),
                            round(rng.uniform(-1.0, 1.0), 2),
                            round(rng.uniform(-1.0, 1.0), 2),
                            "ACCEPTED",
                            "演示审核技师",
                            f"1.2.826.0.1.3680043.10.999.6.{patient.sequence}.{fraction_number}",
                        )
                    )
            _insert_many(
                connection,
                "beam_delivery",
                (
                    "treatment_fraction_id",
                    "beam_id",
                    "delivery_sequence",
                    "specified_meterset_mu",
                    "delivered_meterset_mu",
                    "delivery_start_at",
                    "delivery_end_at",
                    "termination_status",
                    "termination_reason",
                    "machine_record_uid",
                ),
                delivery_rows,
            )
            _insert_many(
                connection,
                "imaging_verification",
                (
                    "treatment_fraction_id",
                    "imaging_type",
                    "acquired_at",
                    "registration_method",
                    "shift_lateral_mm",
                    "shift_longitudinal_mm",
                    "shift_vertical_mm",
                    "rotation_pitch_deg",
                    "rotation_roll_deg",
                    "rotation_yaw_deg",
                    "match_result",
                    "approved_by",
                    "dicom_series_instance_uid",
                ),
                imaging_rows,
            )

            event_rows = [
                (
                    course_id,
                    None,
                    "COURSE_CREATED",
                    _at(oncology.consult_date, 11),
                    "REFERRAL_ACCEPTED",
                    "接收EMR放疗申请并创建疗程",
                    physician_name,
                    None,
                ),
                (
                    course_id,
                    None,
                    "PLAN_APPROVED",
                    _at(simulation_date + timedelta(days=8), 16),
                    "PLAN_REVIEW_OK",
                    "医生与物理师完成计划审批",
                    "演示物理师01",
                    None,
                ),
            ]
            if oncology.course_status == "ON_HOLD":
                hold_fraction = max(1, delivered_target)
                hold_date = fraction_records[hold_fraction][2] or _at(
                    delivered_schedule[hold_fraction - 1], 12
                )
                event_rows.append(
                    (
                        course_id,
                        fraction_records[hold_fraction][0],
                        "TREATMENT_HOLD",
                        hold_date,
                        "TOXICITY_REVIEW",
                        "出现2级毒性，暂停治疗并进行临床评估",
                        physician_name,
                        None,
                    )
                )
            if oncology.course_status == "COMPLETED" and actual_end:
                event_rows.append(
                    (
                        course_id,
                        fraction_records[oncology.fraction_count][0],
                        "COURSE_COMPLETED",
                        _at(actual_end, 18),
                        "PRESCRIPTION_COMPLETE",
                        "计划分次和处方剂量已完成",
                        physician_name,
                        _at(actual_end, 18),
                    )
                )
            _insert_many(
                connection,
                "treatment_event",
                (
                    "treatment_course_id",
                    "treatment_fraction_id",
                    "event_type",
                    "event_at",
                    "event_reason_code",
                    "event_description",
                    "recorded_by",
                    "resolved_at",
                ),
                event_rows,
            )

            toxicity_rows: list[tuple[Any, ...]] = []
            toxicity_by_site = {
                "LUNG": ("PNEUMONITIS", "放射性肺炎"),
                "BREAST": ("DERMATITIS", "放射性皮炎"),
                "PROSTATE": ("URINARY_FREQUENCY", "尿频"),
                "RECTUM": ("DIARRHEA", "腹泻"),
                "NASOPHARYNX": ("MUCOSITIS", "口腔黏膜炎"),
                "BRAIN": ("FATIGUE", "疲乏"),
                "CERVIX": ("DIARRHEA", "腹泻"),
                "ESOPHAGUS": ("DYSPHAGIA", "吞咽困难"),
                "LIVER": ("NAUSEA", "恶心"),
            }
            toxicity_code, toxicity_name = toxicity_by_site.get(
                oncology.site_code, ("FATIGUE", "疲乏")
            )
            for fraction_number in range(1, delivered_target + 1, 5):
                assessment_date = delivered_schedule[fraction_number - 1]
                grade = min(
                    3,
                    int((fraction_number / oncology.fraction_count) * 4)
                    + (1 if patient.sequence % 13 == 0 else 0),
                )
                toxicity_rows.append(
                    (
                        course_id,
                        assessment_date,
                        "5.0",
                        toxicity_code,
                        toxicity_name,
                        grade,
                        "PROBABLE" if grade >= 2 else "POSSIBLE",
                        "加强对症处理并复评" if grade >= 2 else "继续观察",
                        physician_name,
                    )
                )
            _insert_many(
                connection,
                "toxicity_assessment",
                (
                    "treatment_course_id",
                    "assessment_date",
                    "ctcae_version",
                    "toxicity_code",
                    "toxicity_name",
                    "grade",
                    "attribution",
                    "action_taken",
                    "assessed_by",
                ),
                toxicity_rows,
            )

            delivered_fraction_count = sum(
                1
                for status in fraction_status_by_number.values()
                if status in {"DELIVERED", "PARTIALLY_DELIVERED"}
            )
            partial_count = sum(
                1
                for status in fraction_status_by_number.values()
                if status == "PARTIALLY_DELIVERED"
            )
            missed_count = sum(
                1 for status in fraction_status_by_number.values() if status == "MISSED"
            )
            delivered_total = round(sum(delivered_dose_by_number.values()), 3)
            summary_status = (
                "COMPLETED"
                if oncology.course_status == "COMPLETED"
                else (
                    "DISCONTINUED"
                    if oncology.course_status == "DISCONTINUED"
                    else "PLANNED" if delivered_fraction_count == 0 else "IN_PROGRESS"
                )
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dose_summary (
                        treatment_course_id, prescribed_total_dose_gy, delivered_total_dose_gy,
                        prescribed_fraction_count, delivered_fraction_count, partial_fraction_count,
                        missed_fraction_count, first_treatment_date, last_treatment_date,
                        summary_status, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        course_id,
                        oncology.total_dose_gy,
                        delivered_total,
                        oncology.fraction_count,
                        delivered_fraction_count,
                        partial_count,
                        missed_count,
                        oncology.planned_start_date if delivered_fraction_count else None,
                        (
                            delivered_schedule[max(0, delivered_target - 1)]
                            if delivered_fraction_count
                            else None
                        ),
                        summary_status,
                        datetime(2026, 8, 29, 12),
                    ),
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def configure_read_only_and_dblink() -> None:
    for source_database in DATABASES:
        connection = _admin_connection(source_database)
        try:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS dblink")
                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(QUERY_ROLE))
                )
                cursor.execute(
                    sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(
                        sql.Identifier(QUERY_ROLE)
                    )
                )
                cursor.execute(
                    sql.SQL("GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                        sql.Identifier(QUERY_ROLE)
                    )
                )
                cursor.execute(
                    sql.SQL(
                        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}"
                    ).format(sql.Identifier(QUERY_ROLE))
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def verify_dblink() -> dict[str, int]:
    verification_sql = {
        "emr_demo": """
            SELECT count(*)
            FROM patient e
            JOIN dblink('pms_demo_conn', $$SELECT mpi_id FROM portal_account$$)
              AS p(mpi_id varchar) ON p.mpi_id = e.mpi_id
            JOIN dblink('rvs_demo_conn', $$SELECT mpi_id FROM rt_patient$$)
              AS r(mpi_id varchar) ON r.mpi_id = e.mpi_id
        """,
        "pms_demo": """
            SELECT count(*)
            FROM portal_account p
            JOIN dblink('emr_demo_conn', $$SELECT mpi_id FROM patient$$)
              AS e(mpi_id varchar) ON e.mpi_id = p.mpi_id
            JOIN dblink('rvs_demo_conn', $$SELECT mpi_id FROM rt_patient$$)
              AS r(mpi_id varchar) ON r.mpi_id = p.mpi_id
        """,
        "rvs_demo": """
            SELECT count(*)
            FROM rt_patient r
            JOIN dblink('emr_demo_conn', $$SELECT mpi_id FROM patient$$)
              AS e(mpi_id varchar) ON e.mpi_id = r.mpi_id
            JOIN dblink('pms_demo_conn', $$SELECT mpi_id FROM portal_account$$)
              AS p(mpi_id varchar) ON p.mpi_id = r.mpi_id
        """,
    }
    results: dict[str, int] = {}
    for source_database in DATABASES:
        connection = _query_connection(source_database)
        try:
            with connection.cursor() as cursor:
                for target_database in DATABASES:
                    if target_database == source_database:
                        continue
                    conninfo = make_dsn(
                        host=DBLINK_HOST,
                        port=DBLINK_PORT,
                        dbname=target_database,
                        user=QUERY_ROLE,
                        password=QUERY_PASSWORD,
                        options="-csearch_path= -cdefault_transaction_read_only=on",
                    )
                    cursor.execute(
                        "SELECT dblink_connect(%s, %s)",
                        (f"{target_database}_conn", conninfo),
                    )
                cursor.execute(verification_sql[source_database])
                results[source_database] = int(cursor.fetchone()[0])
                for target_database in DATABASES:
                    if target_database != source_database:
                        cursor.execute("SELECT dblink_disconnect(%s)", (f"{target_database}_conn",))
        finally:
            connection.close()
    return results


def collect_counts() -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for database in DATABASES:
        connection = _query_connection(database)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
                )
                table_names = [row[0] for row in cursor.fetchall()]
                database_counts: dict[str, int] = {}
                for table_name in table_names:
                    cursor.execute(
                        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table_name))
                    )
                    database_counts[table_name] = int(cursor.fetchone()[0])
                counts[database] = database_counts
        finally:
            connection.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate only emr_demo, pms_demo, and rvs_demo if they already exist",
    )
    args = parser.parse_args()

    print("Preparing persistent EMR/PMS/RVS synthetic demo databases...")
    patients = build_patients()
    try:
        create_role_and_databases(recreate=args.recreate)
        apply_schema("emr_demo", "emr_schema.sql")
        apply_schema("pms_demo", "pms_schema.sql")
        apply_schema("rvs_demo", "rvs_schema.sql")
        emr_result = seed_emr(patients)
        seed_pms(patients, emr_result)
        seed_rvs(patients)
        configure_read_only_and_dblink()
        dblink_results = verify_dblink()
        counts = collect_counts()
    except Exception as exc:
        print(f"Initialization failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Initialization completed successfully.")
    for database, table_counts in counts.items():
        print(f"- {database}: {len(table_counts)} tables, " f"{sum(table_counts.values())} rows")
    print("Three-database MPI overlap from each possible primary:")
    for database, overlap_count in dblink_results.items():
        print(f"- {database}: {overlap_count} patients")
    print(f"Read-only application role: {QUERY_ROLE}")
    print("Database passwords were not printed.")


if __name__ == "__main__":
    main()
