-- Synthetic patient-facing Patient Management/Portal System schema.
-- Appointment is a booking; the resulting clinical Encounter remains owned by EMR.

CREATE TABLE portal_account (
    portal_account_id BIGSERIAL PRIMARY KEY,
    account_number VARCHAR(32) NOT NULL UNIQUE,
    mpi_id VARCHAR(32) NOT NULL UNIQUE,
    emr_medical_record_number VARCHAR(32) NOT NULL,
    display_name VARCHAR(64) NOT NULL,
    mobile_phone VARCHAR(24),
    email VARCHAR(160),
    identity_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_level VARCHAR(20) NOT NULL CHECK (
        verification_level IN ('UNVERIFIED', 'MOBILE_VERIFIED', 'REAL_NAME_VERIFIED')
    ),
    preferred_language VARCHAR(16) NOT NULL DEFAULT 'zh-CN',
    account_status VARCHAR(20) NOT NULL CHECK (
        account_status IN ('PENDING', 'ACTIVE', 'LOCKED', 'CLOSED')
    ),
    registered_at TIMESTAMP NOT NULL,
    last_login_at TIMESTAMP,
    synthetic_identity BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE portal_account IS '患者端账号，与EMR患者通过MPI ID关联，不等同于患者临床记录';
COMMENT ON COLUMN portal_account.mpi_id IS '跨EMR、PMS、RVS关联同一合成患者的主患者索引';

CREATE TABLE appointment (
    appointment_id BIGSERIAL PRIMARY KEY,
    appointment_number VARCHAR(40) NOT NULL UNIQUE,
    portal_account_id BIGINT NOT NULL REFERENCES portal_account(portal_account_id),
    mpi_id VARCHAR(32) NOT NULL,
    service_category VARCHAR(32) NOT NULL,
    service_code VARCHAR(32) NOT NULL,
    service_name VARCHAR(160) NOT NULL,
    department_code VARCHAR(32) NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    practitioner_no VARCHAR(32),
    practitioner_name VARCHAR(64),
    scheduled_start_at TIMESTAMP NOT NULL,
    scheduled_end_at TIMESTAMP NOT NULL,
    appointment_status VARCHAR(20) NOT NULL CHECK (
        appointment_status IN ('PROPOSED', 'PENDING', 'BOOKED', 'ARRIVED', 'FULFILLED', 'CANCELLED', 'NOSHOW')
    ),
    participant_status VARCHAR(20) NOT NULL CHECK (
        participant_status IN ('NEEDS_ACTION', 'ACCEPTED', 'DECLINED', 'TENTATIVE')
    ),
    booking_channel VARCHAR(20) NOT NULL CHECK (
        booking_channel IN ('APP', 'WECHAT', 'WEB', 'CALL_CENTER', 'CLINIC')
    ),
    reason_code VARCHAR(32),
    reason_text VARCHAR(240),
    cancellation_reason VARCHAR(240),
    external_emr_encounter_number VARCHAR(40),
    external_course_uid VARCHAR(64),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT ck_appointment_period CHECK (scheduled_end_at > scheduled_start_at),
    CONSTRAINT ck_appointment_cancellation CHECK (
        cancellation_reason IS NULL OR appointment_status IN ('CANCELLED', 'NOSHOW')
    )
);
COMMENT ON TABLE appointment IS '患者预约的医疗事件；履约后可引用EMR实际Encounter，放疗预约可引用RVS疗程';
CREATE INDEX idx_appointment_mpi_time ON appointment(mpi_id, scheduled_start_at DESC);
CREATE INDEX idx_appointment_status_time ON appointment(appointment_status, scheduled_start_at);
CREATE INDEX idx_appointment_course ON appointment(external_course_uid);

CREATE TABLE appointment_status_history (
    appointment_status_history_id BIGSERIAL PRIMARY KEY,
    appointment_id BIGINT NOT NULL REFERENCES appointment(appointment_id) ON DELETE CASCADE,
    from_status VARCHAR(20),
    to_status VARCHAR(20) NOT NULL,
    changed_at TIMESTAMP NOT NULL,
    changed_by_type VARCHAR(20) NOT NULL CHECK (
        changed_by_type IN ('PATIENT', 'STAFF', 'SYSTEM', 'EXTERNAL_SYSTEM')
    ),
    change_reason VARCHAR(240)
);
COMMENT ON TABLE appointment_status_history IS '预约状态流转审计，例如待确认、已预约、到达、履约、取消和爽约';
CREATE INDEX idx_appointment_history ON appointment_status_history(appointment_id, changed_at);

CREATE TABLE questionnaire (
    questionnaire_id SERIAL PRIMARY KEY,
    questionnaire_code VARCHAR(32) NOT NULL UNIQUE,
    questionnaire_name VARCHAR(160) NOT NULL,
    questionnaire_version VARCHAR(16) NOT NULL,
    questionnaire_purpose VARCHAR(32) NOT NULL CHECK (
        questionnaire_purpose IN ('PRE_VISIT', 'SYMPTOM_ASSESSMENT', 'PATIENT_REPORTED_OUTCOME', 'SATISFACTION')
    ),
    active_from DATE NOT NULL,
    active_to DATE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (questionnaire_code, questionnaire_version)
);
COMMENT ON TABLE questionnaire IS '患者端可填写的问卷定义，包括就诊前信息、症状和患者报告结局';

CREATE TABLE questionnaire_item (
    questionnaire_item_id SERIAL PRIMARY KEY,
    questionnaire_id INT NOT NULL REFERENCES questionnaire(questionnaire_id) ON DELETE CASCADE,
    item_code VARCHAR(32) NOT NULL,
    item_text VARCHAR(300) NOT NULL,
    answer_type VARCHAR(20) NOT NULL CHECK (
        answer_type IN ('BOOLEAN', 'INTEGER', 'DECIMAL', 'CHOICE', 'TEXT')
    ),
    unit VARCHAR(24),
    display_order INT NOT NULL,
    required BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (questionnaire_id, item_code)
);
COMMENT ON TABLE questionnaire_item IS '问卷条目及答案类型';

CREATE TABLE questionnaire_response (
    questionnaire_response_id BIGSERIAL PRIMARY KEY,
    response_number VARCHAR(40) NOT NULL UNIQUE,
    questionnaire_id INT NOT NULL REFERENCES questionnaire(questionnaire_id),
    portal_account_id BIGINT NOT NULL REFERENCES portal_account(portal_account_id),
    mpi_id VARCHAR(32) NOT NULL,
    appointment_id BIGINT REFERENCES appointment(appointment_id),
    external_course_uid VARCHAR(64),
    response_status VARCHAR(20) NOT NULL CHECK (
        response_status IN ('IN_PROGRESS', 'COMPLETED', 'AMENDED', 'STOPPED')
    ),
    authored_at TIMESTAMP NOT NULL,
    submitted_at TIMESTAMP,
    total_score NUMERIC(8, 2),
    risk_level VARCHAR(16) CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))
);
COMMENT ON TABLE questionnaire_response IS '患者提交的问卷实例，可关联预约或RVS放疗疗程';
CREATE INDEX idx_questionnaire_response_mpi_time ON questionnaire_response(mpi_id, authored_at DESC);
CREATE INDEX idx_questionnaire_response_course ON questionnaire_response(external_course_uid);

CREATE TABLE questionnaire_answer (
    questionnaire_answer_id BIGSERIAL PRIMARY KEY,
    questionnaire_response_id BIGINT NOT NULL REFERENCES questionnaire_response(questionnaire_response_id) ON DELETE CASCADE,
    questionnaire_item_id INT NOT NULL REFERENCES questionnaire_item(questionnaire_item_id),
    value_boolean BOOLEAN,
    value_numeric NUMERIC(12, 3),
    value_code VARCHAR(32),
    value_text VARCHAR(500),
    CONSTRAINT ck_questionnaire_answer_value CHECK (
        num_nonnulls(value_boolean, value_numeric, value_code, value_text) = 1
    ),
    UNIQUE (questionnaire_response_id, questionnaire_item_id)
);
COMMENT ON TABLE questionnaire_answer IS '问卷条目的结构化答案，每条答案只使用一个值字段';

CREATE TABLE consent_record (
    consent_record_id BIGSERIAL PRIMARY KEY,
    consent_number VARCHAR(40) NOT NULL UNIQUE,
    portal_account_id BIGINT NOT NULL REFERENCES portal_account(portal_account_id),
    mpi_id VARCHAR(32) NOT NULL,
    consent_scope VARCHAR(32) NOT NULL CHECK (
        consent_scope IN ('PRIVACY', 'PORTAL_SERVICE', 'TELEMEDICINE', 'RADIOTHERAPY', 'DATA_SHARING')
    ),
    policy_version VARCHAR(24) NOT NULL,
    consent_status VARCHAR(20) NOT NULL CHECK (
        consent_status IN ('PROPOSED', 'ACTIVE', 'REJECTED', 'WITHDRAWN', 'EXPIRED')
    ),
    decision VARCHAR(12) NOT NULL CHECK (decision IN ('PERMIT', 'DENY')),
    effective_from TIMESTAMP NOT NULL,
    effective_to TIMESTAMP,
    signed_at TIMESTAMP,
    signature_method VARCHAR(24),
    external_course_uid VARCHAR(64),
    CONSTRAINT ck_consent_period CHECK (effective_to IS NULL OR effective_to > effective_from)
);
COMMENT ON TABLE consent_record IS '患者对隐私、患者端服务、远程医疗、放疗或数据共享作出的版本化许可或拒绝';
CREATE INDEX idx_consent_mpi_scope ON consent_record(mpi_id, consent_scope, effective_from DESC);

CREATE TABLE message_thread (
    message_thread_id BIGSERIAL PRIMARY KEY,
    thread_number VARCHAR(40) NOT NULL UNIQUE,
    portal_account_id BIGINT NOT NULL REFERENCES portal_account(portal_account_id),
    mpi_id VARCHAR(32) NOT NULL,
    thread_topic VARCHAR(32) NOT NULL CHECK (
        thread_topic IN ('APPOINTMENT', 'MEDICATION', 'BILLING', 'RADIOTHERAPY', 'GENERAL')
    ),
    external_course_uid VARCHAR(64),
    thread_status VARCHAR(16) NOT NULL CHECK (thread_status IN ('OPEN', 'RESOLVED', 'CLOSED')),
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP
);
COMMENT ON TABLE message_thread IS '患者与医护团队之间的安全消息会话';
CREATE INDEX idx_message_thread_mpi_time ON message_thread(mpi_id, opened_at DESC);

CREATE TABLE secure_message (
    secure_message_id BIGSERIAL PRIMARY KEY,
    message_thread_id BIGINT NOT NULL REFERENCES message_thread(message_thread_id) ON DELETE CASCADE,
    sender_type VARCHAR(20) NOT NULL CHECK (sender_type IN ('PATIENT', 'CLINICIAN', 'CARE_TEAM', 'SYSTEM')),
    sender_display VARCHAR(64) NOT NULL,
    sent_at TIMESTAMP NOT NULL,
    read_at TIMESTAMP,
    message_category VARCHAR(24) NOT NULL,
    message_text TEXT NOT NULL,
    urgent BOOLEAN NOT NULL DEFAULT FALSE
);
COMMENT ON TABLE secure_message IS '患者端安全消息；内容为合成的结构化业务场景文本';
CREATE INDEX idx_secure_message_thread_time ON secure_message(message_thread_id, sent_at);

CREATE TABLE bill (
    bill_id BIGSERIAL PRIMARY KEY,
    bill_number VARCHAR(40) NOT NULL UNIQUE,
    portal_account_id BIGINT NOT NULL REFERENCES portal_account(portal_account_id),
    mpi_id VARCHAR(32) NOT NULL,
    external_emr_encounter_number VARCHAR(40),
    external_course_uid VARCHAR(64),
    bill_type VARCHAR(24) NOT NULL CHECK (
        bill_type IN ('OUTPATIENT', 'INPATIENT', 'IMAGING', 'RADIOTHERAPY')
    ),
    issued_at TIMESTAMP NOT NULL,
    due_at TIMESTAMP,
    gross_amount NUMERIC(12, 2) NOT NULL CHECK (gross_amount >= 0),
    insurance_amount NUMERIC(12, 2) NOT NULL CHECK (insurance_amount >= 0),
    patient_amount NUMERIC(12, 2) NOT NULL CHECK (patient_amount >= 0),
    outstanding_amount NUMERIC(12, 2) NOT NULL CHECK (outstanding_amount >= 0),
    bill_status VARCHAR(20) NOT NULL CHECK (
        bill_status IN ('DRAFT', 'OPEN', 'PARTIALLY_PAID', 'PAID', 'VOID', 'REFUNDED')
    )
);
COMMENT ON TABLE bill IS '患者端展示的医疗费用账单，可追踪EMR就诊或RVS疗程';
CREATE INDEX idx_bill_mpi_status ON bill(mpi_id, bill_status, issued_at DESC);

CREATE TABLE payment_transaction (
    payment_transaction_id BIGSERIAL PRIMARY KEY,
    transaction_number VARCHAR(48) NOT NULL UNIQUE,
    bill_id BIGINT NOT NULL REFERENCES bill(bill_id),
    transaction_type VARCHAR(16) NOT NULL CHECK (transaction_type IN ('PAYMENT', 'REFUND')),
    payment_method VARCHAR(24) NOT NULL CHECK (
        payment_method IN ('WECHAT_PAY', 'ALIPAY', 'BANK_CARD', 'INSURANCE_ACCOUNT', 'CASH_DESK')
    ),
    payment_channel VARCHAR(20) NOT NULL CHECK (payment_channel IN ('APP', 'WEB', 'COUNTER', 'AUTOMATIC')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    transaction_status VARCHAR(20) NOT NULL CHECK (
        transaction_status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'REVERSED')
    ),
    requested_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    provider_reference VARCHAR(64)
);
COMMENT ON TABLE payment_transaction IS '患者端发起或展示的支付和退款交易';
CREATE INDEX idx_payment_bill_time ON payment_transaction(bill_id, requested_at DESC);

CREATE TABLE notification (
    notification_id BIGSERIAL PRIMARY KEY,
    portal_account_id BIGINT NOT NULL REFERENCES portal_account(portal_account_id),
    mpi_id VARCHAR(32) NOT NULL,
    notification_type VARCHAR(32) NOT NULL CHECK (
        notification_type IN ('APPOINTMENT_REMINDER', 'RESULT_AVAILABLE', 'PAYMENT_DUE', 'RADIOTHERAPY_REMINDER', 'MESSAGE_RECEIVED')
    ),
    delivery_channel VARCHAR(16) NOT NULL CHECK (delivery_channel IN ('APP_PUSH', 'SMS', 'EMAIL', 'WECHAT')),
    scheduled_at TIMESTAMP NOT NULL,
    delivered_at TIMESTAMP,
    delivery_status VARCHAR(20) NOT NULL CHECK (
        delivery_status IN ('PENDING', 'DELIVERED', 'FAILED', 'CANCELLED')
    ),
    reference_type VARCHAR(32),
    reference_number VARCHAR(64),
    title VARCHAR(160) NOT NULL,
    content_text VARCHAR(500) NOT NULL
);
COMMENT ON TABLE notification IS '患者端预约、结果、缴费、放疗分次和消息提醒的发送记录';
CREATE INDEX idx_notification_account_time ON notification(portal_account_id, scheduled_at DESC);
