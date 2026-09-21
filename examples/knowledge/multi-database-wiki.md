# EMR、PMS、RVS 的患者身份与跨系统关联

本说明适用于仓库的合成医疗数据示例。上传时选择 `emr_demo`、`pms_demo`、`rvs_demo` 三个逻辑数据库。

## 患者身份

MPI 是这三个系统共享的业务患者标识。每个库内自己的患者 ID、账号 ID 和病历号不能直接替代 MPI 用于跨系统关联。

```text
emr_demo.public.patient.mpi_id = pms_demo.public.portal_account.mpi_id
emr_demo.public.patient.mpi_id = rvs_demo.public.rt_patient.mpi_id
```

这些关系来自业务约定，不是数据库建立的跨库外键。本说明没有声明它们的唯一性或完整覆盖率。

## 申请单与疗程

以下字段用于关联 EMR 的放疗申请与 RVS 的疗程：

```text
emr_demo.public.service_request.request_number = rvs_demo.public.treatment_course.source_request_number
```

查询申请对应的疗程时，应保留申请单粒度。仅按患者关联不能证明某一疗程对应某一申请。

## 业务事件的区别

PMS 的预约是计划发生的事件。EMR 的 encounter 是实际就诊记录。RVS 的 delivered fraction 是治疗分次的实际交付记录。预约存在不证明实际就诊或治疗已经发生。

## 查询依据

字段的实际名称和类型以数据库当前 Schema 为准。涉及多个业务事件的一对多连接时，需要先确定结果粒度，避免主表金额或次数被重复累加。
