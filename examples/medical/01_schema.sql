-- ============================================================================
-- 01_schema.sql
-- 医疗信息系统建表脚本 (PostgreSQL)
-- 包含：基础数据、门诊、住院、诊断/医技、药房、财务
-- ============================================================================

-- SET search_path TO medical, public; -- 使用默认 public schema

-- ============================================================================
-- 1. 基础数据模块 (Base Data)
-- ============================================================================

-- 1.1 科室表
CREATE TABLE department (
    dept_id SERIAL PRIMARY KEY,
    dept_code VARCHAR(20) NOT NULL UNIQUE,
    dept_name VARCHAR(50) NOT NULL,
    dept_type VARCHAR(20) CHECK (dept_type IN ('CLINICAL', 'MEDICAL_TECH', 'ADMIN', 'LOGISTICS')), -- 临床, 医技, 行政, 后勤
    parent_dept_id INT, -- 上级科室ID
    manager_id INT, -- 科室主任ID (暂不设FK，避免循环依赖)
    status INT DEFAULT 1 CHECK (status IN (0, 1)), -- 0:停用, 1:启用
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE department IS '科室信息表';
COMMENT ON COLUMN department.dept_id IS '科室ID';
COMMENT ON COLUMN department.dept_code IS '科室编码';
COMMENT ON COLUMN department.dept_name IS '科室名称';
COMMENT ON COLUMN department.dept_type IS '科室类型: CLINICAL-临床, MEDICAL_TECH-医技, ADMIN-行政';
COMMENT ON COLUMN department.parent_dept_id IS '父级科室ID';

-- 1.2 员工表 (医生、护士、行政)
CREATE TABLE employee (
    emp_id SERIAL PRIMARY KEY,
    job_number VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    gender VARCHAR(10) CHECK (gender IN ('M', 'F')),
    birth_date DATE,
    id_card VARCHAR(18) UNIQUE,
    phone VARCHAR(20),
    dept_id INT REFERENCES department(dept_id),
    title VARCHAR(20), -- 职称: 主任医师, 主治医师, 护师等
    role_type VARCHAR(20) CHECK (role_type IN ('DOCTOR', 'NURSE', 'TECH', 'ADMIN')),
    entry_date DATE,
    status INT DEFAULT 1
);
COMMENT ON TABLE employee IS '员工信息表';
COMMENT ON COLUMN employee.emp_id IS '员工ID';
COMMENT ON COLUMN employee.name IS '姓名';
COMMENT ON COLUMN employee.title IS '职称';
COMMENT ON COLUMN employee.role_type IS '角色类型: DOCTOR-医生, NURSE-护士';

-- 1.3 患者基本信息表
CREATE TABLE patient (
    patient_id SERIAL PRIMARY KEY,
    mpi_id VARCHAR(32) UNIQUE NOT NULL, -- 主索引ID
    name VARCHAR(50) NOT NULL,
    gender VARCHAR(10),
    birth_date DATE,
    id_card VARCHAR(18) UNIQUE,
    phone VARCHAR(20),
    address VARCHAR(200),
    insurance_type_code VARCHAR(20), -- 医保类型
    abo_blood_type VARCHAR(5), -- ABO血型
    rh_blood_type VARCHAR(5), -- Rh血型
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE patient IS '患者基本信息表';
COMMENT ON COLUMN patient.mpi_id IS '患者主索引ID (Master Patient Index)';
COMMENT ON COLUMN patient.insurance_type_code IS '医保类型代码';

-- 1.4 医保类型字典
CREATE TABLE insurance_type (
    code VARCHAR(20) PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    payment_ratio DECIMAL(5,2) -- 报销比例
);
COMMENT ON TABLE insurance_type IS '医保类型字典表';

-- 1.5 药品字典表
CREATE TABLE drug_dictionary (
    drug_id SERIAL PRIMARY KEY,
    drug_code VARCHAR(20) UNIQUE,
    common_name VARCHAR(100) NOT NULL, -- 通用名
    trade_name VARCHAR(100), -- 商品名
    spec VARCHAR(100), -- 规格
    dosage_form VARCHAR(50), -- 剂型
    unit VARCHAR(20), -- 单位
    price DECIMAL(10,2), -- 单价
    manufacturer VARCHAR(100), -- 厂家
    antibiotic_level INT DEFAULT 0, -- 抗生素级别
    is_prescription BOOLEAN DEFAULT TRUE, -- 是否处方药
    stock_quantity INT DEFAULT 0
);
COMMENT ON TABLE drug_dictionary IS '药品字典及库存表';

-- 1.6 诊疗项目/收费项目字典
CREATE TABLE charge_item (
    item_id SERIAL PRIMARY KEY,
    item_code VARCHAR(20) UNIQUE,
    item_name VARCHAR(100) NOT NULL,
    item_type VARCHAR(20), -- 检查, 检验, 治疗, 手术, 材料
    price DECIMAL(10,2),
    dept_id INT REFERENCES department(dept_id), -- 执行科室
    is_active BOOLEAN DEFAULT TRUE
);
COMMENT ON TABLE charge_item IS '收费项目字典表';

-- ============================================================================
-- 2. 门诊模块 (Outpatient)
-- ============================================================================

-- 2.1 医生排班表
CREATE TABLE schedule (
    schedule_id SERIAL PRIMARY KEY,
    doctor_id INT REFERENCES employee(emp_id),
    dept_id INT REFERENCES department(dept_id),
    schedule_date DATE NOT NULL,
    shift_type VARCHAR(10) CHECK (shift_type IN ('MORNING', 'AFTERNOON', 'NIGHT')),
    limit_count INT DEFAULT 30, -- 号源数量
    reg_count INT DEFAULT 0, -- 已挂号数量
    status INT DEFAULT 1
);
COMMENT ON TABLE schedule IS '医生排班表';

-- 2.2 挂号记录表
CREATE TABLE registration (
    reg_id SERIAL PRIMARY KEY,
    ticket_no VARCHAR(20) NOT NULL, -- 票号
    patient_id INT REFERENCES patient(patient_id),
    schedule_id INT REFERENCES schedule(schedule_id),
    dept_id INT REFERENCES department(dept_id),
    doctor_id INT REFERENCES employee(emp_id),
    reg_type VARCHAR(20) NOT NULL, -- 普通号, 专家号, 急诊
    reg_fee DECIMAL(10,2), -- 挂号费
    reg_status VARCHAR(20) DEFAULT 'WAITING', -- WAITING:候诊, COMPLETED:已诊, CANCELED:退号
    reg_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    visit_time TIMESTAMP -- 就诊时间
);
COMMENT ON TABLE registration IS '挂号记录表';

-- 2.3 门诊就诊记录 (电子病历封面)
CREATE TABLE outpatient_visit (
    visit_id SERIAL PRIMARY KEY,
    reg_id INT REFERENCES registration(reg_id),
    patient_id INT REFERENCES patient(patient_id),
    doctor_id INT REFERENCES employee(emp_id),
    visit_date DATE,
    chief_complaint TEXT, -- 主诉
    history_present_illness TEXT, -- 现病史
    history_past_illness TEXT, -- 既往史
    physical_exam TEXT, -- 体格检查
    diagnosis_desc TEXT, -- 初步诊断描述
    advice TEXT -- 医嘱建议
);
COMMENT ON TABLE outpatient_visit IS '门诊就诊记录表';

-- 2.4 门诊处方头表
CREATE TABLE prescription (
    presc_id SERIAL PRIMARY KEY,
    visit_id INT REFERENCES outpatient_visit(visit_id),
    patient_id INT REFERENCES patient(patient_id),
    doctor_id INT REFERENCES employee(emp_id),
    presc_type VARCHAR(20), -- 西药, 中药
    diagnoses TEXT,
    total_amount DECIMAL(10,2),
    presc_status VARCHAR(20) DEFAULT 'CREATED', -- CREATED, PAID, DISPENSED, COMPLETED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE prescription IS '门诊处方表';

-- 2.5 门诊处方明细表
CREATE TABLE prescription_detail (
    detail_id SERIAL PRIMARY KEY,
    presc_id INT REFERENCES prescription(presc_id),
    drug_id INT REFERENCES drug_dictionary(drug_id),
    dosage VARCHAR(50), -- 用量 (每次2片)
    usage_method VARCHAR(50), -- 用法 (口服, 静滴)
    frequency VARCHAR(50), -- 频次 (tid, bid)
    quantity INT, -- 总量
    unit_price DECIMAL(10,2),
    amount DECIMAL(10,2),
    group_no INT DEFAULT 1 -- 组号 (同组药)
);
COMMENT ON TABLE prescription_detail IS '处方明细表';

-- ============================================================================
-- 3. 住院模块 (HIS / Inpatient)
-- ============================================================================

-- 3.1 病区表
CREATE TABLE ward (
    ward_id SERIAL PRIMARY KEY,
    ward_name VARCHAR(50) NOT NULL,
    dept_id INT REFERENCES department(dept_id), -- 所属科室
    location VARCHAR(100) -- 位置
);
COMMENT ON TABLE ward IS '病区信息表';

-- 3.2 床位表
CREATE TABLE bed (
    bed_id SERIAL PRIMARY KEY,
    ward_id INT REFERENCES ward(ward_id),
    bed_code VARCHAR(20) NOT NULL,
    room_no VARCHAR(20),
    status VARCHAR(20) DEFAULT 'EMPTY', -- EMPTY:空床, OCCUPIED:占用, MAINTAIN:维修
    current_patient_id INT -- 当前患者 (非FK，仅引用)
);
COMMENT ON TABLE bed IS '床位信息表';

-- 3.3 住院登记表 (核心表)
CREATE TABLE admission (
    admission_id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES patient(patient_id),
    dept_id INT REFERENCES department(dept_id), -- 入院科室
    ward_id INT REFERENCES ward(ward_id), -- 入院病区
    bed_id INT REFERENCES bed(bed_id),
    attending_doctor_id INT REFERENCES employee(emp_id), -- 主治医生
    admission_date TIMESTAMP NOT NULL,
    discharge_date TIMESTAMP,
    status VARCHAR(20) CHECK (status IN ('ADMITTED', 'DISCHARGED', 'TRANSFERRED')),
    primary_diagnosis TEXT, -- 入院诊断
    prepayment_balance DECIMAL(12,2) DEFAULT 0.00 -- 预交金余额
);
COMMENT ON TABLE admission IS '住院登记表';

-- 3.4 长期/临时医嘱表
CREATE TABLE admission_order (
    order_id SERIAL PRIMARY KEY,
    admission_id INT REFERENCES admission(admission_id),
    patient_id INT REFERENCES patient(patient_id),
    doctor_id INT REFERENCES employee(emp_id), -- 开嘱医生
    order_type VARCHAR(10) CHECK (order_type IN ('LONG', 'TEMP')), -- 长期/临时
    order_content VARCHAR(500) NOT NULL, -- 医嘱内容 (可以是药品名或处置)
    drug_id INT REFERENCES drug_dictionary(drug_id), -- 如果是药品
    item_id INT REFERENCES charge_item(item_id), -- 如果是诊疗项目
    dosage VARCHAR(50),
    frequency VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'ACTIVE' -- ACTIVE, STOPPED, EXECUTED
);
COMMENT ON TABLE admission_order IS '住院医嘱表';

-- 3.5 护理记录
CREATE TABLE nursing_record (
    record_id SERIAL PRIMARY KEY,
    admission_id INT REFERENCES admission(admission_id),
    nurse_id INT REFERENCES employee(emp_id),
    record_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    temperature DECIMAL(4,1), -- 体温
    pulse INT, -- 脉搏
    respiration INT, -- 呼吸
    blood_pressure_sys INT, -- 收缩压
    blood_pressure_dia INT, -- 舒张压
    consciousness VARCHAR(50), -- 意识
    notes TEXT -- 护理记录内容
);
COMMENT ON TABLE nursing_record IS '护理记录及体征表';

-- 3.6 手术记录表
CREATE TABLE surgery (
    surgery_id SERIAL PRIMARY KEY,
    admission_id INT REFERENCES admission(admission_id),
    patient_id INT REFERENCES patient(patient_id),
    surgeon_id INT REFERENCES employee(emp_id), -- 主刀医生
    anesthetist_id INT REFERENCES employee(emp_id), -- 麻醉师
    surgery_name VARCHAR(200) NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    anesthesia_method VARCHAR(50), -- 麻醉方式
    complications TEXT, -- 并发症
    surgery_level VARCHAR(10) -- 手术级别: 一级, 二级...
);
COMMENT ON TABLE surgery IS '手术记录表';

-- ============================================================================
-- 4. 诊断与医技模块 (Diagnosis & LIS/PACS)
-- ============================================================================

-- 4.1 ICD-10 诊断字典
CREATE TABLE diagnosis_dictionary (
    diag_code VARCHAR(20) PRIMARY KEY,
    diag_name VARCHAR(200) NOT NULL,
    pinyin_code VARCHAR(50),
    diag_type VARCHAR(20) -- 西医, 中医
);
COMMENT ON TABLE diagnosis_dictionary IS 'ICD-10诊断字典表';

-- 4.2 患者诊断记录 (门诊+住院)
CREATE TABLE patient_diagnosis (
    pd_id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES patient(patient_id),
    visit_id INT REFERENCES outpatient_visit(visit_id), -- 可为空
    admission_id INT REFERENCES admission(admission_id), -- 可为空
    doctor_id INT REFERENCES employee(emp_id),
    diag_code VARCHAR(20) REFERENCES diagnosis_dictionary(diag_code),
    diag_type VARCHAR(20) DEFAULT 'WESTERN', -- WESTERN, TCM
    is_primary BOOLEAN DEFAULT FALSE, -- 是否主诊断
    diag_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE patient_diagnosis IS '患者诊断记录表';

-- 4.3 检查/检验申请单 (Request)
CREATE TABLE inspection_request (
    request_id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES patient(patient_id),
    visit_id INT REFERENCES outpatient_visit(visit_id),
    admission_id INT REFERENCES admission(admission_id),
    req_doctor_id INT REFERENCES employee(emp_id), -- 申请医生
    req_dept_id INT REFERENCES department(dept_id), -- 申请科室
    exec_dept_id INT REFERENCES department(dept_id), -- 执行科室
    item_id INT REFERENCES charge_item(item_id), -- 检查项目
    req_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    clinical_diag TEXT, -- 临床诊断
    status VARCHAR(20) DEFAULT 'REQUESTED' -- REQUESTED, SAMPLE_COLLECTED, REPORTED
);
COMMENT ON TABLE inspection_request IS '检查检验申请单';

-- 4.4 检查/检验结果 (Result)
CREATE TABLE inspection_result (
    result_id SERIAL PRIMARY KEY,
    request_id INT REFERENCES inspection_request(request_id),
    report_doctor_id INT REFERENCES employee(emp_id), -- 报告医生
    audit_doctor_id INT REFERENCES employee(emp_id), -- 审核医生
    report_time TIMESTAMP,
    finding TEXT, -- 检查所见
    conclusion TEXT, -- 诊断结论
    image_url VARCHAR(500), -- 影像链接(如有)
    is_abnormal BOOLEAN DEFAULT FALSE, -- 是危急值/异常
    device_name VARCHAR(100) -- 检查设备
);
COMMENT ON TABLE inspection_result IS '检查检验报告结果表';

-- ============================================================================
-- 5. 财务模块 (Finance)
-- ============================================================================

-- 5.1 费用明细流水表 (核心大表)
CREATE TABLE fee_record (
    fee_id BIGSERIAL PRIMARY KEY,
    patient_id INT REFERENCES patient(patient_id),
    visit_id INT REFERENCES outpatient_visit(visit_id),
    admission_id INT REFERENCES admission(admission_id),
    item_id INT REFERENCES charge_item(item_id), -- 项目
    drug_id INT REFERENCES drug_dictionary(drug_id), -- 或药品
    unit_price DECIMAL(10,2) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL, -- 应收
    discount_amount DECIMAL(10,2) DEFAULT 0.00,
    pay_amount DECIMAL(10,2) NOT NULL, -- 实收
    fee_type VARCHAR(20), -- DRUG, EXAM, TREAT, BED...
    dept_id INT REFERENCES department(dept_id), -- 开单科室
    exec_dept_id INT REFERENCES department(dept_id), -- 执行科室
    fee_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(10) DEFAULT 'NORMAL' -- NORMAL, REFUND
);
COMMENT ON TABLE fee_record IS '费用明细流水表';
CREATE INDEX idx_fee_patient ON fee_record(patient_id);
CREATE INDEX idx_fee_time ON fee_record(fee_time);

-- 5.2 结算记录表
CREATE TABLE settlement (
    settle_id SERIAL PRIMARY KEY,
    patient_id INT REFERENCES patient(patient_id),
    visit_id INT REFERENCES outpatient_visit(visit_id),
    admission_id INT REFERENCES admission(admission_id),
    total_cost DECIMAL(12,2), -- 总费用
    insurance_pay DECIMAL(12,2), -- 医保支付
    self_pay DECIMAL(12,2), -- 自费支付
    settle_type VARCHAR(20), -- OUTPATIENT, INPATIENT
    settle_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    operator_id INT REFERENCES employee(emp_id), -- 收费员
    invoice_no VARCHAR(50) -- 发票号
);
COMMENT ON TABLE settlement IS '费用结算记录表';

-- 5.3 支付记录表
CREATE TABLE payment (
    pay_id SERIAL PRIMARY KEY,
    settle_id INT REFERENCES settlement(settle_id),
    pay_method VARCHAR(20), -- CASH, WECHAT, ALIPAY, BANK
    amount DECIMAL(12,2),
    transaction_id VARCHAR(100), -- 交易流水号
    pay_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON TABLE payment IS '支付方式记录表';

-- ============================================================================
-- 6. 视图定义 (Views)
-- ============================================================================

-- 6.1 门诊医生工作量统计视图
CREATE OR REPLACE VIEW v_doctor_workload AS
SELECT 
    e.name AS doctor_name,
    d.dept_name,
    COUNT(r.reg_id) AS visit_count,
    SUM(r.reg_fee) AS total_reg_fee
FROM registration r
JOIN employee e ON r.doctor_id = e.emp_id
JOIN department d ON r.dept_id = d.dept_id
WHERE r.reg_status = 'COMPLETED'
GROUP BY e.name, d.dept_name;

-- 6.2 患者全景视图 (360视图)
CREATE OR REPLACE VIEW v_patient_360 AS
SELECT 
    p.patient_id,
    p.name,
    p.gender,
    EXTRACT(YEAR FROM AGE(p.birth_date)) AS age,
    COUNT(DISTINCT ov.visit_id) AS outpatient_times,
    COUNT(DISTINCT a.admission_id) AS inpatient_times,
    MAX(ov.visit_date) AS last_visit_date,
    MAX(a.admission_date) AS last_admission_date
FROM patient p
LEFT JOIN outpatient_visit ov ON p.patient_id = ov.patient_id
LEFT JOIN admission a ON p.patient_id = a.patient_id
GROUP BY p.patient_id, p.name, p.gender, p.birth_date;
