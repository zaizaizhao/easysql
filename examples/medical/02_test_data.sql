-- ============================================================================
-- 02_test_data.sql
-- 医疗信息系统测试数据生成脚本
-- 使用 PostgreSQL 语法生成模拟数据
-- ============================================================================

-- SET search_path TO medical, public;

-- ============================================================================
-- 1. 基础字典数据 (Dictionaries)
-- ============================================================================

-- 1.1 医保类型
INSERT INTO insurance_type (code, name, payment_ratio) VALUES
('INS_001', '城镇职工医保', 0.85),
('INS_002', '城乡居民医保', 0.60),
('INS_003', '自费', 0.00);

-- 1.2 科室 (Departments)
INSERT INTO department (dept_code, dept_name, dept_type, parent_dept_id) VALUES
('DEPT_001', '心血管内科', 'CLINICAL', NULL),
('DEPT_002', '呼吸内科', 'CLINICAL', NULL),
('DEPT_003', '普外科', 'CLINICAL', NULL),
('DEPT_004', '骨科', 'CLINICAL', NULL),
('DEPT_005', '妇产科', 'CLINICAL', NULL),
('DEPT_006', '儿科', 'CLINICAL', NULL),
('DEPT_007', '急诊科', 'CLINICAL', NULL),
('DEPT_008', '检验科', 'MEDICAL_TECH', NULL),
('DEPT_009', '放射科', 'MEDICAL_TECH', NULL),
('DEPT_010', '药剂科', 'MEDICAL_TECH', NULL);

-- 1.3 员工 (Employees) - 生成 20 名医生和护士
INSERT INTO employee (job_number, name, gender, dept_id, title, role_type, status)
SELECT 
    'EMP_' || lpad(i::text, 3, '0'),
    (ARRAY['张伟', '王芳', '李娜', '刘强', '陈杰', '杨敏', '赵军', '黄艳', '周磊', '吴霞', 
           '徐刚', '孙丽', '马超', '朱琳', '胡斌', '林婷', '郭涛', '何燕', '罗伟', '高强'])[i],
    CASE WHEN i % 2 = 0 THEN 'F' ELSE 'M' END,
    (i % 10) + 1, -- dept_id 1-10
    CASE WHEN i <= 10 THEN '主治医师' ELSE '主管护师' END,
    CASE WHEN i <= 10 THEN 'DOCTOR' ELSE 'NURSE' END,
    1
FROM generate_series(1, 20) i;

-- 1.4 药品字典 (Drugs)
INSERT INTO drug_dictionary (drug_code, common_name, trade_name, spec, unit, price, is_prescription) VALUES
('DRUG_001', '阿莫西林胶囊', '阿莫仙', '0.25g*24粒', '盒', 12.50, TRUE),
('DRUG_002', '布洛芬缓释胶囊', '芬必得', '0.3g*20粒', '盒', 18.00, FALSE),
('DRUG_003', '头孢拉定胶囊', '先锋六号', '0.25g*24粒', '盒', 8.50, TRUE),
('DRUG_004', '阿司匹林肠溶片', '拜阿司匹林', '100mg*30片', '盒', 15.20, TRUE),
('DRUG_005', '二甲双胍片', '格华止', '0.5g*20片', '盒', 22.50, TRUE),
('DRUG_006', '硝苯地平控释片', '拜新同', '30mg*7片', '盒', 32.10, TRUE),
('DRUG_007', '阿托伐他汀钙片', '立普妥', '20mg*7片', '盒', 45.00, TRUE),
('DRUG_008', '蒙脱石散', '思密达', '3g*10袋', '盒', 18.50, FALSE),
('DRUG_009', '板蓝根颗粒', '白云山', '10g*20袋', '包', 10.00, FALSE),
('DRUG_010', '葡萄糖注射液', NULL, '500ml:25g', '瓶', 3.50, TRUE);

-- 1.5 收费项目 (Charge Items)
INSERT INTO charge_item (item_code, item_name, item_type, price, dept_id) VALUES
('ITEM_001', '普通挂号费', '挂号', 10.00, NULL),
('ITEM_002', '专家挂号费', '挂号', 30.00, NULL),
('ITEM_003', '急诊挂号费', '挂号', 20.00, NULL),
('ITEM_004', '血常规五分类', '检验', 18.00, 8),
('ITEM_005', '尿常规', '检验', 12.00, 8),
('ITEM_006', '肝功能七项', '检验', 85.00, 8),
('ITEM_007', '肾功能三项', '检验', 45.00, 8),
('ITEM_008', '空腹血糖', '检验', 8.00, 8),
('ITEM_009', '胸部正位片(DR)', '检查', 75.00, 9),
('ITEM_010', '腹部B超', '检查', 120.00, 9),
('ITEM_011', '头颅CT平扫', '检查', 240.00, 9),
('ITEM_012', '心电图(12导联)', '检查', 26.00, 1),
('ITEM_013', '静脉输液', '治疗', 15.00, NULL),
('ITEM_014', '肌肉注射', '治疗', 5.00, NULL),
('ITEM_015', '清创缝合术(小)', '手术', 150.00, 7);

-- 1.6 诊断字典 (Diagnosis)
INSERT INTO diagnosis_dictionary (diag_code, diag_name, diag_type) VALUES
('A09.900', '胃肠炎', 'WESTERN'),
('J00.x00', '急性鼻咽炎(感冒)', 'WESTERN'),
('J15.900', '细菌性肺炎', 'WESTERN'),
('I10.x00', '原发性高血压', 'WESTERN'),
('E11.900', '2型糖尿病', 'WESTERN'),
('K29.500', '慢性胃炎', 'WESTERN'),
('M51.200', '腰椎间盘突出', 'WESTERN'),
('S06.000', '脑震荡', 'WESTERN'),
('R50.900', '发热', 'WESTERN'),
('K35.800', '急性阑尾炎', 'WESTERN');

-- 1.7 病区与床位 (Wards & Beds)
INSERT INTO ward (ward_name, dept_id, location) VALUES
('心内科一病区', 1, '住院楼3F'),
('普外科二病区', 3, '住院楼5F'),
('骨科三病区', 4, '住院楼6F');

-- 生成 30 张床位
INSERT INTO bed (ward_id, bed_code, room_no, status)
SELECT 
    (i % 3) + 1,
    'BED_' || lpad(i::text, 3, '0'),
    'ROOM_' || ((i / 3)::int + 1),
    'EMPTY'
FROM generate_series(1, 30) i;

-- ============================================================================
-- 2. 患者数据 (Patients) - 生成 50 名患者
-- ============================================================================
INSERT INTO patient (mpi_id, name, gender, birth_date, id_card, phone, insurance_type_code)
SELECT 
    'MPI_' || lpad(i::text, 6, '0'),
    'Patient_' || i,
    CASE WHEN random() > 0.5 THEN 'M' ELSE 'F' END,
    current_date - (floor(random() * 80 * 365) || ' days')::interval,
    '330101' || (1940 + floor(random()*80))::text || '0101' || lpad(i::text, 4, '0'),
    '1380000' || lpad(i::text, 4, '0'),
    CASE WHEN random() < 0.3 THEN 'INS_001' 
         WHEN random() < 0.6 THEN 'INS_002' 
         ELSE 'INS_003' END
FROM generate_series(1, 50) i;

-- ============================================================================
-- 3. 门诊流程数据 (Outpatient Flow)
-- ============================================================================

-- 3.1 排班 (Schedule) - 生成最近7天的排班
INSERT INTO schedule (doctor_id, dept_id, schedule_date, shift_type)
SELECT 
    (i % 10) + 1, -- 前10个是医生
    ((i % 10) + 1), -- 对应的科室
    current_date - (i % 7) * INTERVAL '1 day',
    CASE WHEN i % 2 = 0 THEN 'MORNING' ELSE 'AFTERNOON' END
FROM generate_series(1, 20) i;

-- 3.2 挂号 (Registration) - 生成 50 条挂号记录
INSERT INTO registration (ticket_no, patient_id, schedule_id, dept_id, doctor_id, reg_type, reg_fee, reg_status, reg_time)
SELECT 
    'TICKET_' || i,
    (i % 50) + 1,
    (i % 20) + 1,
    1, -- 简化，都挂科室1 (or random)
    (i % 10) + 1, -- 医生
    '普通号',
    10.00,
    CASE WHEN i <= 40 THEN 'COMPLETED' ELSE 'WAITING' END, -- 40个已诊，10个候诊
    current_date - (i % 10) * INTERVAL '1 day' + '08:00:00'
FROM generate_series(1, 50) i;

-- 3.3 门诊就诊 (Visits) - 为 40 个已诊患者生成就诊记录
INSERT INTO outpatient_visit (reg_id, patient_id, doctor_id, visit_date, chief_complaint, diagnosis_desc)
SELECT 
    reg_id,
    patient_id,
    doctor_id,
    reg_time::date,
    '主诉：持续咳嗽三天，伴有发热。',
    '初步诊断：急性上呼吸道感染'
FROM registration
WHERE reg_status = 'COMPLETED';

-- 3.4 诊断 (Diagnosis)
INSERT INTO patient_diagnosis (patient_id, visit_id, doctor_id, diag_code, is_primary)
SELECT 
    v.patient_id,
    v.visit_id,
    v.doctor_id,
    (SELECT diag_code FROM diagnosis_dictionary ORDER BY random() LIMIT 1),
    TRUE
FROM outpatient_visit v;

-- 3.5 处方 (Prescriptions) - 每个就诊记录生成一张处方
INSERT INTO prescription (visit_id, patient_id, doctor_id, presc_type, diagnoses, total_amount, presc_status)
SELECT 
    visit_id,
    patient_id,
    doctor_id,
    '西药',
    '急性上呼吸道感染',
    0, -- 稍后更新
    'COMPLETED'
FROM outpatient_visit;

-- 3.6 处方明细 (Details) - 每个处方生成 2 个药品
INSERT INTO prescription_detail (presc_id, drug_id, dosage, quantity, unit_price, amount)
SELECT 
    p.presc_id,
    d.drug_id,
    '2片',
    1,
    d.price,
    d.price
FROM prescription p
CROSS JOIN LATERAL (
    SELECT * FROM drug_dictionary ORDER BY random() LIMIT 2
) d;

-- 更新处方总金额
UPDATE prescription p
SET total_amount = (SELECT SUM(amount) FROM prescription_detail pd WHERE pd.presc_id = p.presc_id);

-- ============================================================================
-- 4. 财务数据 (Finance)
-- ============================================================================

-- 4.1 费用记录 (Fee Records) - 基于处方生成费用
INSERT INTO fee_record (patient_id, visit_id, drug_id, unit_price, quantity, total_amount, pay_amount, fee_type, fee_time)
SELECT 
    p.patient_id,
    p.visit_id,
    pd.drug_id,
    pd.unit_price,
    pd.quantity,
    pd.amount,
    pd.amount, -- 简化：实收=应收
    'DRUG',
    p.created_at
FROM prescription p
JOIN prescription_detail pd ON p.presc_id = pd.presc_id;

-- ============================================================================
-- 5. 住院流程 (Inpatient Flow) - 少量数据
-- ============================================================================

-- 生成 5 条住院记录
INSERT INTO admission (patient_id, dept_id, ward_id, bed_id, attending_doctor_id, admission_date, status)
SELECT 
    (i % 50) + 1,
    1, -- 心内科
    1, -- 心内一病区
    i, -- Bed 1-5
    1, -- 医生1
    current_date - 10 * INTERVAL '1 day',
    'ADMITTED'
FROM generate_series(1, 5) i;

-- 更新床位状态
UPDATE bed SET status = 'OCCUPIED' WHERE bed_id <= 5;

-- 医嘱
INSERT INTO admission_order (admission_id, patient_id, doctor_id, order_type, order_content, drug_id, start_time)
SELECT 
    admission_id,
    patient_id,
    attending_doctor_id,
    'LONG',
    '阿司匹林肠溶片 100mg qd',
    4,
    admission_date
FROM admission;

-- ============================================================================
-- 6. 检查检验数据 (Inspection)
-- ============================================================================

-- 6.1 门诊检查申请 (item_id: 4-12 是检验检查项目, 11 是头颅CT平扫)
INSERT INTO inspection_request (patient_id, visit_id, admission_id, req_doctor_id, req_dept_id, exec_dept_id, item_id, req_time, clinical_diag, status)
SELECT 
    v.patient_id,
    v.visit_id,
    NULL,
    v.doctor_id,
    1,
    CASE WHEN i <= 5 THEN 8 ELSE 9 END,
    CASE 
        WHEN i = 1 THEN 4
        WHEN i = 2 THEN 5
        WHEN i = 3 THEN 6
        WHEN i = 4 THEN 11
        ELSE 12
    END,
    v.visit_date + (i || ' hours')::interval,
    '门诊检查',
    'REPORTED'
FROM outpatient_visit v
CROSS JOIN generate_series(1, 5) i
WHERE v.visit_id <= 10;

-- 6.2 住院检查申请 (住院患者做CT)
INSERT INTO inspection_request (patient_id, visit_id, admission_id, req_doctor_id, req_dept_id, exec_dept_id, item_id, req_time, clinical_diag, status)
SELECT 
    a.patient_id,
    NULL,
    a.admission_id,
    a.attending_doctor_id,
    1,
    9,
    11,
    a.admission_date + '1 day'::interval,
    '住院CT检查',
    'REPORTED'
FROM admission a;

-- 6.3 检查结果
INSERT INTO inspection_result (request_id, report_doctor_id, audit_doctor_id, report_time, finding, conclusion, is_abnormal, device_name)
SELECT 
    ir.request_id,
    (ir.request_id % 10) + 1,
    (ir.request_id % 10) + 2,
    ir.req_time + '2 hours'::interval,
    CASE WHEN ci.item_name LIKE '%CT%' THEN '颅脑CT平扫未见明显异常' ELSE '检查结果正常' END,
    CASE WHEN ci.item_name LIKE '%CT%' THEN '颅脑CT平扫未见明显异常' ELSE '未见异常' END,
    FALSE,
    CASE WHEN ci.item_name LIKE '%CT%' THEN 'GE 128排CT' ELSE NULL END
FROM inspection_request ir
JOIN charge_item ci ON ir.item_id = ci.item_id;
