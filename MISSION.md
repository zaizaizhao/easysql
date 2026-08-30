# Mission: EasySQL 的 Langfuse 评测与 Prompt 迭代闭环

## Why
为 EasySQL 建立一套可重复、可比较、可回滚的 Text2SQL 优化流程：把线上和离线发现的 bad case 沉淀为测试集，用固定数据集验证 Prompt 新版本，并在没有关键回归时安全发布。

## Success looks like
- 能把一条生产 Trace 连同人工纠错结果转成可追溯的 Langfuse Dataset Item
- 能固定 Prompt、模型、检索配置和数据集版本运行 Experiment，并比较基线与候选版本
- 能用结果集等价、Schema Linking、执行成功率和失败分类判断改动是否真的变好
- 能把通过门禁的 Prompt 版本晋级为 production，并在回归时恢复旧版本

## Constraints
- 方案必须贴合 EasySQL 当前 LangGraph、Neo4j、Milvus、SQLAlchemy 和 FastAPI 结构
- Langfuse 负责 Prompt、Trace、Dataset、Experiment 和 Score 的生命周期，不替代 Text2SQL 专用判分逻辑
- 不把密钥、生产数据明文或不可序列化的 Langfuse SDK 对象写入 LangGraph checkpoint
- 优先建立小而高价值的内部 golden set，再逐步扩大数据量

## Out of scope
- 本轮不直接实现完整评测模块、前端反馈界面或数据库迁移
- 本轮不接入 Spider、BIRD 等公开 benchmark
- 本轮不做自动 Prompt 改写器或自动线上发布
