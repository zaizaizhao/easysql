-- Synthetic hospital EMR schema informed by WS 445 and HL7 FHIR clinical concepts.
-- Cross-system identifiers are VARCHAR business keys; there are no cross-database FKs.

CREATE TABLE organization (
    organization_id SERIAL PRIMARY KEY,
    organization_code VARCHAR(32) NOT NULL UNIQUE,
    organization_name VARCHAR(160) NOT NULL,
    organization_type VARCHAR(32) NOT NULL,
    province VARCHAR(32) NOT NULL,
    city VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE organization IS '医疗机构主数据，表示维护电子病历的医院或院区';

CREATE TABLE department (
    department_id SERIAL PRIMARY KEY,
    organization_id INT NOT NULL REFERENCES organization(organization_id),
    department_code VARCHAR(32) NOT NULL UNIQUE,
    department_name VARCHAR(100) NOT NULL,
    specialty_code VARCHAR(32),
    outpatient_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    inpatient_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE department IS '医院科室主数据，包括肿瘤科、放疗科、呼吸科等';

CREATE TABLE practitioner (
    practitioner_id SERIAL PRIMARY KEY,
    practitioner_no VARCHAR(32) NOT NULL UNIQUE,
    practitioner_name VARCHAR(64) NOT NULL,
    department_id INT NOT NULL REFERENCES department(department_id),
    professional_title VARCHAR(40) NOT NULL,
    specialty VARCHAR(80),
    license_token VARCHAR(64) NOT NULL UNIQUE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE practitioner IS '参与诊疗活动的医务人员；证件号为不可用于现实身份的合成标识';

CREATE TABLE patient (
    patient_id BIGSERIAL PRIMARY KEY,
    mpi_id VARCHAR(32) NOT NULL UNIQUE,
    medical_record_number VARCHAR(32) NOT NULL UNIQUE,
    patient_name VARCHAR(64) NOT NULL,
    gender_code CHAR(1) NOT NULL CHECK (gender_code IN ('M', 'F', 'U')),
    birth_date DATE NOT NULL,
    id_document_token VARCHAR(32) NOT NULL UNIQUE,
    mobile_phone VARCHAR(24),
    marital_status VARCHAR(20),
    insurance_type_code VARCHAR(32) NOT NULL,
    province VARCHAR(32),
    city VARCHAR(64),
    district VARCHAR(64),
    address_text VARCHAR(200),
    registered_at TIMESTAMP NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    synthetic_identity BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_patient_demo_identity CHECK (id_document_token LIKE 'DEMO-ID-%')
);
COMMENT ON TABLE patient IS '医院患者主记录；全部身份、电话和地址均为确定性生成的虚构演示数据';
COMMENT ON COLUMN patient.mpi_id IS '跨EMR、PMS、RVS关联同一合成患者的主患者索引';
COMMENT ON COLUMN patient.medical_record_number IS '医院EMR内部病案号，不等同于MPI ID';

CREATE TABLE patient_identifier (
    patient_identifier_id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id) ON DELETE CASCADE,
    identifier_system VARCHAR(64) NOT NULL,
    identifier_value VARCHAR(64) NOT NULL,
    identifier_use VARCHAR(20) NOT NULL CHECK (identifier_use IN ('USUAL', 'OFFICIAL', 'SECONDARY')),
    valid_from DATE NOT NULL,
    valid_to DATE,
    UNIQUE (identifier_system, identifier_value)
);
COMMENT ON TABLE patient_identifier IS '患者在院内不同业务域中的业务标识，例如MPI、MRN、医保演示号';

CREATE TABLE encounter (
    encounter_id BIGSERIAL PRIMARY KEY,
    encounter_number VARCHAR(40) NOT NULL UNIQUE,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_class VARCHAR(20) NOT NULL CHECK (
        encounter_class IN ('OUTPATIENT', 'INPATIENT', 'EMERGENCY', 'TELEHEALTH')
    ),
    encounter_status VARCHAR(20) NOT NULL CHECK (
        encounter_status IN ('PLANNED', 'ARRIVED', 'IN_PROGRESS', 'FINISHED', 'CANCELLED')
    ),
    department_id INT NOT NULL REFERENCES department(department_id),
    attending_practitioner_id INT NOT NULL REFERENCES practitioner(practitioner_id),
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP,
    chief_complaint VARCHAR(500),
    admission_source VARCHAR(40),
    discharge_disposition VARCHAR(40),
    source_appointment_number VARCHAR(40),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_encounter_period CHECK (end_at IS NULL OR end_at >= start_at)
);
COMMENT ON TABLE encounter IS '实际发生的门诊、住院、急诊或远程诊疗活动，与PMS预约相区分';
COMMENT ON COLUMN encounter.source_appointment_number IS '来自PMS的预约号，仅作跨系统追踪，不是数据库外键';
CREATE INDEX idx_encounter_patient_start ON encounter(patient_id, start_at DESC);
CREATE INDEX idx_encounter_department_start ON encounter(department_id, start_at DESC);

CREATE TABLE diagnosis (
    diagnosis_id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_id BIGINT NOT NULL REFERENCES encounter(encounter_id) ON DELETE CASCADE,
    code_system VARCHAR(32) NOT NULL DEFAULT 'ICD-10',
    diagnosis_code VARCHAR(20) NOT NULL,
    diagnosis_name VARCHAR(160) NOT NULL,
    diagnosis_type VARCHAR(20) NOT NULL CHECK (
        diagnosis_type IN ('PRIMARY', 'SECONDARY', 'COMORBIDITY', 'PATHOLOGY')
    ),
    clinical_status VARCHAR(20) NOT NULL CHECK (
        clinical_status IN ('ACTIVE', 'RECURRENCE', 'REMISSION', 'RESOLVED')
    ),
    onset_date DATE,
    stage_group VARCHAR(16),
    t_stage VARCHAR(8),
    n_stage VARCHAR(8),
    m_stage VARCHAR(8),
    recorded_at TIMESTAMP NOT NULL,
    verified_by_practitioner_id INT REFERENCES practitioner(practitioner_id)
);
COMMENT ON TABLE diagnosis IS '就诊相关的编码诊断，肿瘤诊断可记录TNM和临床分期';
CREATE INDEX idx_diagnosis_patient_code ON diagnosis(patient_id, diagnosis_code);
CREATE INDEX idx_diagnosis_encounter ON diagnosis(encounter_id);

CREATE TABLE pathology_report (
    pathology_report_id BIGSERIAL PRIMARY KEY,
    pathology_number VARCHAR(40) NOT NULL UNIQUE,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_id BIGINT NOT NULL REFERENCES encounter(encounter_id),
    specimen_type VARCHAR(100) NOT NULL,
    collection_date DATE NOT NULL,
    report_date DATE NOT NULL,
    histology_code VARCHAR(32),
    histology_name VARCHAR(160) NOT NULL,
    differentiation_grade VARCHAR(32),
    er_result VARCHAR(20),
    pr_result VARCHAR(20),
    her2_result VARCHAR(20),
    ki67_percent NUMERIC(5, 2),
    pdl1_cps NUMERIC(6, 2),
    conclusion TEXT NOT NULL
);
COMMENT ON TABLE pathology_report IS '肿瘤病理报告，包括组织学、分化程度及常见生物标志物';
CREATE INDEX idx_pathology_patient ON pathology_report(patient_id, report_date DESC);

CREATE TABLE allergy_intolerance (
    allergy_id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    substance_code VARCHAR(32) NOT NULL,
    substance_name VARCHAR(100) NOT NULL,
    allergy_type VARCHAR(20) NOT NULL CHECK (allergy_type IN ('ALLERGY', 'INTOLERANCE')),
    criticality VARCHAR(12) NOT NULL CHECK (criticality IN ('LOW', 'HIGH', 'UNABLE_TO_ASSESS')),
    reaction_text VARCHAR(200),
    clinical_status VARCHAR(20) NOT NULL CHECK (clinical_status IN ('ACTIVE', 'INACTIVE', 'RESOLVED')),
    recorded_at TIMESTAMP NOT NULL,
    UNIQUE (patient_id, substance_code)
);
COMMENT ON TABLE allergy_intolerance IS '患者过敏和不耐受记录';

CREATE TABLE medication_order (
    medication_order_id BIGSERIAL PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_id BIGINT NOT NULL REFERENCES encounter(encounter_id),
    medication_code VARCHAR(32) NOT NULL,
    medication_name VARCHAR(120) NOT NULL,
    dose_value NUMERIC(10, 3) NOT NULL,
    dose_unit VARCHAR(20) NOT NULL,
    route_code VARCHAR(20) NOT NULL,
    frequency_code VARCHAR(20) NOT NULL,
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP,
    order_status VARCHAR(20) NOT NULL CHECK (
        order_status IN ('ACTIVE', 'COMPLETED', 'STOPPED', 'CANCELLED')
    ),
    prescribing_practitioner_id INT NOT NULL REFERENCES practitioner(practitioner_id)
);
COMMENT ON TABLE medication_order IS '门诊或住院药物医嘱，包括剂量、途径、频次和状态';
CREATE INDEX idx_medication_patient ON medication_order(patient_id, start_at DESC);

CREATE TABLE observation (
    observation_id BIGSERIAL PRIMARY KEY,
    observation_number VARCHAR(40) NOT NULL UNIQUE,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_id BIGINT REFERENCES encounter(encounter_id),
    category_code VARCHAR(24) NOT NULL CHECK (
        category_code IN ('VITAL_SIGNS', 'LABORATORY', 'IMAGING_MEASURE', 'PERFORMANCE_STATUS')
    ),
    observation_code VARCHAR(32) NOT NULL,
    observation_name VARCHAR(120) NOT NULL,
    value_numeric NUMERIC(14, 4),
    value_text VARCHAR(240),
    unit VARCHAR(32),
    reference_range_low NUMERIC(14, 4),
    reference_range_high NUMERIC(14, 4),
    abnormal_flag VARCHAR(12),
    effective_at TIMESTAMP NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'FINAL' CHECK (status IN ('PRELIMINARY', 'FINAL', 'CORRECTED')),
    CONSTRAINT ck_observation_value CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL)
);
COMMENT ON TABLE observation IS '生命体征、实验室结果、影像测量和体能状态等临床观察';
CREATE INDEX idx_observation_patient_code_time ON observation(patient_id, observation_code, effective_at DESC);

CREATE TABLE procedure_record (
    procedure_record_id BIGSERIAL PRIMARY KEY,
    procedure_number VARCHAR(40) NOT NULL UNIQUE,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_id BIGINT NOT NULL REFERENCES encounter(encounter_id),
    procedure_code VARCHAR(32) NOT NULL,
    procedure_name VARCHAR(160) NOT NULL,
    body_site_code VARCHAR(32),
    body_site_name VARCHAR(100),
    procedure_status VARCHAR(20) NOT NULL CHECK (
        procedure_status IN ('PREPARATION', 'IN_PROGRESS', 'COMPLETED', 'NOT_DONE', 'STOPPED')
    ),
    performed_start_at TIMESTAMP NOT NULL,
    performed_end_at TIMESTAMP,
    performer_practitioner_id INT NOT NULL REFERENCES practitioner(practitioner_id),
    outcome_text VARCHAR(500)
);
COMMENT ON TABLE procedure_record IS '已实施的临床操作或治疗处置记录';
CREATE INDEX idx_procedure_patient_time ON procedure_record(patient_id, performed_start_at DESC);

CREATE TABLE imaging_report (
    imaging_report_id BIGSERIAL PRIMARY KEY,
    accession_number VARCHAR(40) NOT NULL UNIQUE,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_id BIGINT NOT NULL REFERENCES encounter(encounter_id),
    modality VARCHAR(16) NOT NULL,
    body_site VARCHAR(80) NOT NULL,
    study_date DATE NOT NULL,
    report_status VARCHAR(20) NOT NULL CHECK (report_status IN ('PRELIMINARY', 'FINAL', 'AMENDED')),
    findings TEXT NOT NULL,
    impression TEXT NOT NULL,
    reporting_practitioner_id INT NOT NULL REFERENCES practitioner(practitioner_id),
    dicom_study_instance_uid VARCHAR(80) NOT NULL UNIQUE
);
COMMENT ON TABLE imaging_report IS '影像检查报告及DICOM Study Instance UID，不保存像素数据';
CREATE INDEX idx_imaging_patient_date ON imaging_report(patient_id, study_date DESC);

CREATE TABLE clinical_document (
    clinical_document_id BIGSERIAL PRIMARY KEY,
    document_number VARCHAR(40) NOT NULL UNIQUE,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_id BIGINT NOT NULL REFERENCES encounter(encounter_id),
    document_type VARCHAR(32) NOT NULL CHECK (
        document_type IN ('OUTPATIENT_NOTE', 'ADMISSION_NOTE', 'PROGRESS_NOTE', 'DISCHARGE_SUMMARY', 'MDT_NOTE')
    ),
    document_title VARCHAR(160) NOT NULL,
    document_status VARCHAR(16) NOT NULL CHECK (document_status IN ('DRAFT', 'FINAL', 'AMENDED')),
    authored_at TIMESTAMP NOT NULL,
    author_practitioner_id INT NOT NULL REFERENCES practitioner(practitioner_id),
    summary_text TEXT NOT NULL
);
COMMENT ON TABLE clinical_document IS '门诊病历、入院记录、病程记录、出院小结和MDT记录';
CREATE INDEX idx_document_patient_time ON clinical_document(patient_id, authored_at DESC);

CREATE TABLE service_request (
    service_request_id BIGSERIAL PRIMARY KEY,
    request_number VARCHAR(40) NOT NULL UNIQUE,
    patient_id BIGINT NOT NULL REFERENCES patient(patient_id),
    encounter_id BIGINT NOT NULL REFERENCES encounter(encounter_id),
    request_type VARCHAR(32) NOT NULL CHECK (
        request_type IN ('LABORATORY', 'IMAGING', 'PATHOLOGY', 'RADIOTHERAPY_CONSULT', 'RADIOTHERAPY_TREATMENT')
    ),
    service_code VARCHAR(32) NOT NULL,
    service_name VARCHAR(160) NOT NULL,
    priority VARCHAR(16) NOT NULL CHECK (priority IN ('ROUTINE', 'URGENT', 'STAT')),
    request_status VARCHAR(20) NOT NULL CHECK (
        request_status IN ('DRAFT', 'ACTIVE', 'ON_HOLD', 'COMPLETED', 'REVOKED')
    ),
    authored_at TIMESTAMP NOT NULL,
    requested_start_date DATE,
    reason_code VARCHAR(32),
    reason_text VARCHAR(240),
    requesting_practitioner_id INT NOT NULL REFERENCES practitioner(practitioner_id),
    destination_system VARCHAR(32)
);
COMMENT ON TABLE service_request IS '临床服务申请；放疗申请号可与RVS疗程的来源申请号关联';
CREATE INDEX idx_service_request_patient_type ON service_request(patient_id, request_type, authored_at DESC);
