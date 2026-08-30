# EMR + PMS + RVS Multi-Database Demo

This example creates three persistent PostgreSQL databases containing correlated, synthetic
oncology-care data for EasySQL multi-database and `dblink` testing:

- `emr_demo`: hospital EMR data such as patient identity, encounters, diagnoses, observations,
  medication orders, documents, and radiotherapy service requests.
- `pms_demo`: patient-facing portal data such as accounts, appointments, consent, questionnaires,
  secure messages, bills, payments, and notifications.
- `rvs_demo`: radiotherapy Record & Verify data such as courses, prescriptions, approved plans,
  fraction groups, beams, delivered fractions, imaging verification, interruptions, and toxicity.

All people and events are deterministic synthetic records. No production or copied patient data is
used. Every record that resembles personal information is marked or formatted as demo data, for
example `MPI-DEMO-000001`, `DEMO-ID-000001`, and `patient0001@example.invalid`.

## Domain basis

The relational model is intentionally pragmatic rather than a literal serialization of standards:

- EMR boundaries and fields are informed by China's WS 445 electronic medical record datasets and
  HL7 FHIR Patient, Encounter, Condition, Observation, Procedure, and ServiceRequest concepts.
- PMS scheduling separates Appointment from the actual EMR Encounter and includes Consent,
  QuestionnaireResponse, Communication-like messages, and financial self-service records.
- RVS follows DICOM RT concepts: RT Plan, Fraction Group, Beam, Treatment Session/Fraction,
  specified and delivered meterset, verification imaging, and treatment termination/hold events.
- IHE Radiation Oncology TDW-II informs the separation between the Treatment Management System
  represented here and the treatment-delivery machine.

See [CONTEXT.md](./CONTEXT.md) for the canonical domain terms.

## Cross-database identity

The three systems share only business identifiers. They do not use cross-database foreign keys:

```text
emr_demo.patient.mpi_id
    = pms_demo.portal_account.mpi_id
    = rvs_demo.rt_patient.mpi_id
```

EMR radiotherapy requests are correlated to RVS courses through:

```text
emr_demo.service_request.request_number
    = rvs_demo.treatment_course.source_request_number
```

PMS radiotherapy appointments are correlated to RVS courses through `external_course_uid`.

## Data volume

The default seed creates roughly:

- 320 EMR patients, including 96 oncology patients referred to radiotherapy.
- More than 900 encounters and more than 1,000 coded diagnoses.
- Portal accounts, longitudinal appointments, consent, symptom questionnaires, secure messages,
  bills, and payments for most patients.
- Around 100 radiotherapy courses with realistic conventional, hypofractionated, and SBRT
  prescriptions.
- Thousands of delivered fractions and beam-delivery records, including partial delivery,
  treatment holds, imaging shifts, missed appointments, and toxicity assessments.

Exact counts are printed by the initializer and can vary only when the seed/version changes.

## Initialize

The initializer is non-destructive by default. It refuses to overwrite an existing demo database.
Use `--recreate` only when replacement is intentional.

Required environment variables:

```bash
export PGHOST=127.0.0.1
export PGPORT=55432
export PGUSER=postgres
export PGPASSWORD='<admin password>'
export DEMO_QUERY_PASSWORD='<password for easysql_demo_ro>'
export DEMO_DBLINK_HOST='easysql-postgres'
```

Run:

```bash
.venv/bin/python examples/multi_medical/init_db.py --recreate
```

The initializer:

1. Creates `emr_demo`, `pms_demo`, and `rvs_demo`.
2. Creates the schemas and deterministic synthetic data.
3. Creates/updates the login role `easysql_demo_ro` and grants read-only access.
4. Installs `dblink` in every demo database.
5. Verifies credential-backed dblink connections without foreign servers or user mappings.
6. Verifies a real three-database join from each possible primary database.

The script never prints database passwords.

`DEMO_DBLINK_HOST` must be the address as seen by PostgreSQL itself. The default Docker Compose
service name forces the loopback dblink connection through SCRAM authentication. Using
`127.0.0.1` with the repository's development `pg_hba.conf` would select its local `trust` rule,
which PostgreSQL intentionally rejects for non-superuser `dblink_connect` calls.

## EasySQL configuration

Register the databases with these logical aliases:

| Logical name | Physical database | Automatic dblink connection |
|---|---|---|
| `emr_demo` | `emr_demo` | `emr_demo_conn` |
| `pms_demo` | `pms_demo` | `pms_demo_conn` |
| `rvs_demo` | `rvs_demo` | `rvs_demo_conn` |

After saving the data sources, run EasySQL's schema synchronization so Neo4j and Milvus receive the
new logical database, schema, table, and column identifiers.

## Suggested acceptance questions

Single-system questions:

- EMR: `统计不同肿瘤诊断的患者数、平均年龄和最近一次就诊时间。`
- PMS: `统计未来七天各科室预约量、取消量和未到诊量。`
- RVS: `查询当前治疗中的放疗患者、已完成分次、计划分次和累计剂量。`

Cross-system questions:

- `查询肺癌患者的姓名、最近一次肿瘤科就诊、患者端最近预约和当前放疗完成进度。`
- `查询发生2级及以上放疗毒性的患者，其EMR诊断、PMS症状问卷分数以及RVS累计剂量。`
- `找出PMS显示已取消放疗预约，但RVS仍记录了当日实际治疗分次的患者。`
- `统计不同肿瘤部位从EMR放疗申请到RVS首个实际治疗分次的等待天数。`

## Standards references

- [China NHC WS 445 electronic medical record dataset series](https://www.nhc.gov.cn/fzs/c100048/201406/077528a74b04441da2ccce0082ce01e9.shtml)
- [HL7 FHIR R4 Patient](https://hl7.org/fhir/R4/patient.html)
- [HL7 FHIR R4 Encounter](https://hl7.org/fhir/R4/encounter.html)
- [HL7 FHIR R4 Appointment](https://hl7.org/fhir/R4/appointment.html)
- [HL7 FHIR R4 Consent](https://hl7.org/fhir/R4/consent.html)
- [DICOM PS3.3 RT Plan IOD](https://dicom.nema.org/medical/dicom/2025d/output/chtml/part03/sect_A.20.html)
- [DICOM PS3.3 RT Fraction Scheme](https://dicom.nema.org/medical/dicom/2025e/output/chtml/part03/sect_C.8.8.13.html)
- [DICOM specified and delivered meterset values](https://dicom.nema.org/medical/dicom/2025a/output/chtml/part03/sect_C.8.8.21.2.html)
- [IHE Radiation Oncology Technical Framework](https://www.ihe.net/resources/technical_frameworks/)
- [PostgreSQL dblink_connect](https://www.postgresql.org/docs/current/contrib-dblink-connect.html)
