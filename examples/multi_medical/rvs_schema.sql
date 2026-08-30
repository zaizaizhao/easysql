-- Synthetic radiotherapy Record & Verify / Treatment Management System schema.
-- Concepts follow DICOM RT Plan, Fraction Group, Beam and Treatment Record semantics.

CREATE TABLE rt_patient (
    rt_patient_id BIGSERIAL PRIMARY KEY,
    rvs_patient_number VARCHAR(32) NOT NULL UNIQUE,
    mpi_id VARCHAR(32) NOT NULL UNIQUE,
    emr_medical_record_number VARCHAR(32) NOT NULL,
    patient_name VARCHAR(64) NOT NULL,
    gender_code CHAR(1) NOT NULL CHECK (gender_code IN ('M', 'F', 'U')),
    birth_date DATE NOT NULL,
    registered_at TIMESTAMP NOT NULL,
    patient_status VARCHAR(16) NOT NULL CHECK (patient_status IN ('ACTIVE', 'INACTIVE', 'DECEASED')),
    synthetic_identity BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE rt_patient IS 'RVS本地患者主记录，通过MPI ID与EMR及PMS关联';
COMMENT ON COLUMN rt_patient.mpi_id IS '跨EMR、PMS、RVS关联同一合成患者的主患者索引';

CREATE TABLE treatment_machine (
    treatment_machine_id SERIAL PRIMARY KEY,
    machine_code VARCHAR(24) NOT NULL UNIQUE,
    machine_name VARCHAR(100) NOT NULL,
    manufacturer VARCHAR(80) NOT NULL,
    model_name VARCHAR(80) NOT NULL,
    machine_type VARCHAR(24) NOT NULL CHECK (
        machine_type IN ('LINAC', 'TOMOTHERAPY', 'CYBERKNIFE', 'BRACHYTHERAPY')
    ),
    supported_energies VARCHAR(160) NOT NULL,
    commissioned_date DATE NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE treatment_machine IS '放射治疗递送设备主数据，例如直线加速器及其可用能量';

CREATE TABLE treatment_course (
    treatment_course_id BIGSERIAL PRIMARY KEY,
    course_uid VARCHAR(64) NOT NULL UNIQUE,
    course_number VARCHAR(40) NOT NULL UNIQUE,
    rt_patient_id BIGINT NOT NULL REFERENCES rt_patient(rt_patient_id),
    mpi_id VARCHAR(32) NOT NULL,
    source_request_number VARCHAR(40) NOT NULL,
    diagnosis_code VARCHAR(20) NOT NULL,
    diagnosis_name VARCHAR(160) NOT NULL,
    treatment_site_code VARCHAR(32) NOT NULL,
    treatment_site_name VARCHAR(120) NOT NULL,
    laterality VARCHAR(16) CHECK (laterality IN ('LEFT', 'RIGHT', 'MIDLINE', 'NOT_APPLICABLE')),
    clinical_stage VARCHAR(20),
    treatment_intent VARCHAR(20) NOT NULL CHECK (
        treatment_intent IN ('CURATIVE', 'ADJUVANT', 'NEOADJUVANT', 'PALLIATIVE', 'PROPHYLACTIC')
    ),
    attending_oncologist_no VARCHAR(32) NOT NULL,
    attending_oncologist_name VARCHAR(64) NOT NULL,
    consult_date DATE NOT NULL,
    simulation_date DATE,
    planned_start_date DATE,
    actual_start_date DATE,
    actual_end_date DATE,
    course_status VARCHAR(20) NOT NULL CHECK (
        course_status IN ('REFERRED', 'SIMULATED', 'PLANNING', 'READY', 'ACTIVE', 'ON_HOLD', 'COMPLETED', 'DISCONTINUED')
    ),
    discontinuation_reason VARCHAR(240),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT ck_course_discontinued_reason CHECK (
        discontinuation_reason IS NULL OR course_status = 'DISCONTINUED'
    )
);
COMMENT ON TABLE treatment_course IS '针对一个诊断、部位和治疗意图的完整放疗疗程';
COMMENT ON COLUMN treatment_course.source_request_number IS '来源EMR放疗服务申请号，仅作跨系统业务关联';
CREATE INDEX idx_course_mpi_status ON treatment_course(mpi_id, course_status, created_at DESC);
CREATE INDEX idx_course_request ON treatment_course(source_request_number);

CREATE TABLE prescription (
    prescription_id BIGSERIAL PRIMARY KEY,
    prescription_number VARCHAR(40) NOT NULL UNIQUE,
    treatment_course_id BIGINT NOT NULL REFERENCES treatment_course(treatment_course_id) ON DELETE CASCADE,
    prescribed_total_dose_gy NUMERIC(7, 3) NOT NULL CHECK (prescribed_total_dose_gy > 0),
    prescribed_fraction_count INT NOT NULL CHECK (prescribed_fraction_count > 0),
    dose_per_fraction_gy NUMERIC(7, 3) NOT NULL CHECK (dose_per_fraction_gy > 0),
    fractions_per_day INT NOT NULL DEFAULT 1 CHECK (fractions_per_day BETWEEN 1 AND 3),
    treatment_days_per_week INT NOT NULL DEFAULT 5 CHECK (treatment_days_per_week BETWEEN 1 AND 7),
    radiation_type VARCHAR(16) NOT NULL CHECK (radiation_type IN ('PHOTON', 'ELECTRON', 'PROTON')),
    technique VARCHAR(20) NOT NULL CHECK (technique IN ('3DCRT', 'IMRT', 'VMAT', 'SBRT', 'SRS')),
    image_guidance_protocol VARCHAR(40) NOT NULL,
    prescription_status VARCHAR(20) NOT NULL CHECK (
        prescription_status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED', 'COMPLETED', 'DISCONTINUED')
    ),
    prescribed_at TIMESTAMP NOT NULL,
    prescribed_by_no VARCHAR(32) NOT NULL,
    prescribed_by_name VARCHAR(64) NOT NULL,
    CONSTRAINT ck_prescription_fractionation CHECK (
        abs(prescribed_total_dose_gy - prescribed_fraction_count * dose_per_fraction_gy) <= 0.2
    )
);
COMMENT ON TABLE prescription IS '疗程的临床放疗处方，包括总剂量、分次、技术和影像引导方案';
CREATE INDEX idx_prescription_course ON prescription(treatment_course_id);

CREATE TABLE rt_plan (
    rt_plan_id BIGSERIAL PRIMARY KEY,
    plan_uid VARCHAR(80) NOT NULL UNIQUE,
    sop_instance_uid VARCHAR(80) NOT NULL UNIQUE,
    treatment_course_id BIGINT NOT NULL REFERENCES treatment_course(treatment_course_id) ON DELETE CASCADE,
    prescription_id BIGINT NOT NULL REFERENCES prescription(prescription_id),
    plan_label VARCHAR(32) NOT NULL,
    plan_name VARCHAR(120) NOT NULL,
    plan_version INT NOT NULL CHECK (plan_version > 0),
    plan_status VARCHAR(20) NOT NULL CHECK (
        plan_status IN ('DRAFT', 'PHYSICS_REVIEW', 'PHYSICIAN_REVIEW', 'APPROVED', 'RETIRED', 'REJECTED')
    ),
    treatment_technique VARCHAR(20) NOT NULL,
    planned_total_dose_gy NUMERIC(7, 3) NOT NULL,
    planned_fraction_count INT NOT NULL,
    dose_calculation_algorithm VARCHAR(80) NOT NULL,
    planning_system VARCHAR(80) NOT NULL,
    planning_system_version VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    approved_at TIMESTAMP,
    approved_by_no VARCHAR(32),
    approved_by_name VARCHAR(64),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_plan_approval CHECK (
        plan_status <> 'APPROVED' OR (approved_at IS NOT NULL AND approved_by_no IS NOT NULL)
    )
);
COMMENT ON TABLE rt_plan IS 'DICOM RT Plan级技术计划，包含版本、审批状态、计划剂量及计划系统信息';
CREATE INDEX idx_rt_plan_course_current ON rt_plan(treatment_course_id, is_current);

CREATE TABLE fraction_group (
    fraction_group_id BIGSERIAL PRIMARY KEY,
    rt_plan_id BIGINT NOT NULL REFERENCES rt_plan(rt_plan_id) ON DELETE CASCADE,
    fraction_group_number INT NOT NULL,
    fraction_pattern VARCHAR(32) NOT NULL,
    number_of_fractions_planned INT NOT NULL CHECK (number_of_fractions_planned > 0),
    number_of_beams INT NOT NULL CHECK (number_of_beams > 0),
    dose_per_fraction_gy NUMERIC(7, 3) NOT NULL CHECK (dose_per_fraction_gy > 0),
    UNIQUE (rt_plan_id, fraction_group_number)
);
COMMENT ON TABLE fraction_group IS 'DICOM RT Fraction Group，对计划中的分次方案和射束集合进行分组';

CREATE TABLE beam (
    beam_id BIGSERIAL PRIMARY KEY,
    rt_plan_id BIGINT NOT NULL REFERENCES rt_plan(rt_plan_id) ON DELETE CASCADE,
    fraction_group_id BIGINT NOT NULL REFERENCES fraction_group(fraction_group_id) ON DELETE CASCADE,
    beam_number INT NOT NULL,
    beam_name VARCHAR(40) NOT NULL,
    beam_type VARCHAR(16) NOT NULL CHECK (beam_type IN ('STATIC', 'DYNAMIC', 'ARC')),
    radiation_type VARCHAR(16) NOT NULL CHECK (radiation_type IN ('PHOTON', 'ELECTRON', 'PROTON')),
    nominal_energy_mev NUMERIC(5, 1) NOT NULL,
    gantry_angle_deg NUMERIC(6, 2),
    collimator_angle_deg NUMERIC(6, 2),
    couch_angle_deg NUMERIC(6, 2),
    planned_meterset_mu NUMERIC(10, 3) NOT NULL CHECK (planned_meterset_mu > 0),
    monitor_unit_rate INT NOT NULL CHECK (monitor_unit_rate > 0),
    control_point_count INT NOT NULL CHECK (control_point_count >= 2),
    UNIQUE (rt_plan_id, beam_number)
);
COMMENT ON TABLE beam IS '计划射束，记录射束编号、能量、几何角度和计划Monitor Unit';
CREATE INDEX idx_beam_fraction_group ON beam(fraction_group_id);

CREATE TABLE treatment_fraction (
    treatment_fraction_id BIGSERIAL PRIMARY KEY,
    treatment_session_uid VARCHAR(80) NOT NULL UNIQUE,
    treatment_course_id BIGINT NOT NULL REFERENCES treatment_course(treatment_course_id) ON DELETE CASCADE,
    rt_plan_id BIGINT NOT NULL REFERENCES rt_plan(rt_plan_id),
    fraction_group_id BIGINT NOT NULL REFERENCES fraction_group(fraction_group_id),
    fraction_number INT NOT NULL CHECK (fraction_number > 0),
    clinical_fraction_number INT NOT NULL CHECK (clinical_fraction_number > 0),
    scheduled_start_at TIMESTAMP NOT NULL,
    actual_start_at TIMESTAMP,
    actual_end_at TIMESTAMP,
    fraction_status VARCHAR(20) NOT NULL CHECK (
        fraction_status IN ('SCHEDULED', 'IN_PROGRESS', 'DELIVERED', 'PARTIALLY_DELIVERED', 'MISSED', 'CANCELLED', 'NOT_DELIVERED')
    ),
    treatment_machine_id INT NOT NULL REFERENCES treatment_machine(treatment_machine_id),
    planned_dose_gy NUMERIC(7, 3) NOT NULL CHECK (planned_dose_gy >= 0),
    delivered_dose_gy NUMERIC(7, 3) NOT NULL DEFAULT 0 CHECK (delivered_dose_gy >= 0),
    setup_note VARCHAR(500),
    therapist_1 VARCHAR(64),
    therapist_2 VARCHAR(64),
    verified_by VARCHAR(64),
    UNIQUE (treatment_course_id, fraction_number),
    CONSTRAINT ck_fraction_delivery_time CHECK (actual_end_at IS NULL OR actual_end_at >= actual_start_at)
);
COMMENT ON TABLE treatment_fraction IS '一次计划或实际放疗分次，记录机器、状态、时间及计划和递送剂量';
CREATE INDEX idx_fraction_course_status ON treatment_fraction(treatment_course_id, fraction_status, fraction_number);
CREATE INDEX idx_fraction_schedule ON treatment_fraction(scheduled_start_at, fraction_status);

CREATE TABLE beam_delivery (
    beam_delivery_id BIGSERIAL PRIMARY KEY,
    treatment_fraction_id BIGINT NOT NULL REFERENCES treatment_fraction(treatment_fraction_id) ON DELETE CASCADE,
    beam_id BIGINT NOT NULL REFERENCES beam(beam_id),
    delivery_sequence INT NOT NULL DEFAULT 1 CHECK (delivery_sequence > 0),
    specified_meterset_mu NUMERIC(10, 3) NOT NULL CHECK (specified_meterset_mu > 0),
    delivered_meterset_mu NUMERIC(10, 3) NOT NULL CHECK (delivered_meterset_mu >= 0),
    delivery_start_at TIMESTAMP,
    delivery_end_at TIMESTAMP,
    termination_status VARCHAR(20) NOT NULL CHECK (
        termination_status IN ('NORMAL', 'PARTIAL', 'INTERRUPTED', 'ABORTED', 'NOT_DELIVERED')
    ),
    termination_reason VARCHAR(240),
    machine_record_uid VARCHAR(80) NOT NULL UNIQUE,
    UNIQUE (treatment_fraction_id, beam_id, delivery_sequence),
    CONSTRAINT ck_beam_delivery_time CHECK (delivery_end_at IS NULL OR delivery_end_at >= delivery_start_at)
);
COMMENT ON TABLE beam_delivery IS 'DICOM Treatment Record语义下单射束计划与实际递送Meterset记录，可记录中断和续照';
CREATE INDEX idx_beam_delivery_fraction ON beam_delivery(treatment_fraction_id);

CREATE TABLE imaging_verification (
    imaging_verification_id BIGSERIAL PRIMARY KEY,
    treatment_fraction_id BIGINT NOT NULL REFERENCES treatment_fraction(treatment_fraction_id) ON DELETE CASCADE,
    imaging_type VARCHAR(20) NOT NULL CHECK (imaging_type IN ('CBCT', 'KV_PAIR', 'MV_PORTAL', 'SURFACE_GUIDANCE')),
    acquired_at TIMESTAMP NOT NULL,
    registration_method VARCHAR(32) NOT NULL,
    shift_lateral_mm NUMERIC(7, 2) NOT NULL,
    shift_longitudinal_mm NUMERIC(7, 2) NOT NULL,
    shift_vertical_mm NUMERIC(7, 2) NOT NULL,
    rotation_pitch_deg NUMERIC(6, 2) NOT NULL DEFAULT 0,
    rotation_roll_deg NUMERIC(6, 2) NOT NULL DEFAULT 0,
    rotation_yaw_deg NUMERIC(6, 2) NOT NULL DEFAULT 0,
    match_result VARCHAR(16) NOT NULL CHECK (match_result IN ('ACCEPTED', 'REPEATED', 'REJECTED')),
    approved_by VARCHAR(64) NOT NULL,
    dicom_series_instance_uid VARCHAR(80) NOT NULL UNIQUE
);
COMMENT ON TABLE imaging_verification IS '分次治疗前的影像引导和配准位移记录';
CREATE INDEX idx_imaging_verification_fraction ON imaging_verification(treatment_fraction_id);

CREATE TABLE treatment_event (
    treatment_event_id BIGSERIAL PRIMARY KEY,
    treatment_course_id BIGINT NOT NULL REFERENCES treatment_course(treatment_course_id) ON DELETE CASCADE,
    treatment_fraction_id BIGINT REFERENCES treatment_fraction(treatment_fraction_id),
    event_type VARCHAR(24) NOT NULL CHECK (
        event_type IN ('COURSE_CREATED', 'PLAN_APPROVED', 'TREATMENT_HOLD', 'TREATMENT_RESUME', 'BEAM_INTERRUPTION', 'PLAN_CHANGE', 'MACHINE_SWITCH', 'COURSE_COMPLETED')
    ),
    event_at TIMESTAMP NOT NULL,
    event_reason_code VARCHAR(32),
    event_description VARCHAR(500) NOT NULL,
    recorded_by VARCHAR(64) NOT NULL,
    resolved_at TIMESTAMP
);
COMMENT ON TABLE treatment_event IS '疗程审批、暂停、恢复、射束中断、换机、改计划和完成等事件审计';
CREATE INDEX idx_treatment_event_course_time ON treatment_event(treatment_course_id, event_at);

CREATE TABLE toxicity_assessment (
    toxicity_assessment_id BIGSERIAL PRIMARY KEY,
    treatment_course_id BIGINT NOT NULL REFERENCES treatment_course(treatment_course_id) ON DELETE CASCADE,
    assessment_date DATE NOT NULL,
    ctcae_version VARCHAR(16) NOT NULL DEFAULT '5.0',
    toxicity_code VARCHAR(32) NOT NULL,
    toxicity_name VARCHAR(120) NOT NULL,
    grade INT NOT NULL CHECK (grade BETWEEN 0 AND 5),
    attribution VARCHAR(20) NOT NULL CHECK (
        attribution IN ('UNRELATED', 'UNLIKELY', 'POSSIBLE', 'PROBABLE', 'DEFINITE')
    ),
    action_taken VARCHAR(240),
    assessed_by VARCHAR(64) NOT NULL,
    UNIQUE (treatment_course_id, assessment_date, toxicity_code)
);
COMMENT ON TABLE toxicity_assessment IS '按CTCAE版本记录放疗期间或随访期毒性及分级';
CREATE INDEX idx_toxicity_course_grade ON toxicity_assessment(treatment_course_id, grade, assessment_date);

CREATE TABLE dose_summary (
    dose_summary_id BIGSERIAL PRIMARY KEY,
    treatment_course_id BIGINT NOT NULL UNIQUE REFERENCES treatment_course(treatment_course_id) ON DELETE CASCADE,
    prescribed_total_dose_gy NUMERIC(7, 3) NOT NULL,
    delivered_total_dose_gy NUMERIC(7, 3) NOT NULL,
    prescribed_fraction_count INT NOT NULL,
    delivered_fraction_count INT NOT NULL,
    partial_fraction_count INT NOT NULL DEFAULT 0,
    missed_fraction_count INT NOT NULL DEFAULT 0,
    first_treatment_date DATE,
    last_treatment_date DATE,
    summary_status VARCHAR(20) NOT NULL CHECK (
        summary_status IN ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'DISCONTINUED')
    ),
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT ck_dose_summary_counts CHECK (
        delivered_fraction_count >= 0 AND delivered_fraction_count <= prescribed_fraction_count
    )
);
COMMENT ON TABLE dose_summary IS '疗程级处方剂量与累计实际递送剂量、分次和状态汇总';
