完整任务清单
一、Session 持久化存储
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 1.1 | 实现 PostgreSQL Session 存储 | easysql_api/services/pg_session_store.py | 使用已有的 migrations/001_create_session_tables.sql 表结构 |
| 1.2 | 添加 is_few_shot 字段 | migrations/002_add_few_shot_flag.sql | easysql_messages 表添加 is_few_shot BOOLEAN DEFAULT FALSE |
| 1.3 | 添加存储后端配置 | easysql/config.py | `session_backend: str = "memory" | "postgres"` |
| 1.4 | 切换存储实现 | easysql_api/services/session_store.py | 根据配置选择内存或 PostgreSQL |
---
二、Few-Shot 配置
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 2.1 | 添加 Few-Shot 配置项 | easysql/config.py | few_shot_enabled, few_shot_max_examples, few_shot_min_similarity |
---
三、Few-Shot 存储层（Milvus）
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 3.1 | 创建 FewShotWriter | easysql/writers/few_shot_writer.py | create_collection(), insert(), delete() |
| 3.2 | 创建 FewShotReader | easysql/readers/few_shot_reader.py | search_similar(db_name, query), list_by_db(), get_by_id() |
Collection Schema: id, db_name(隔离), question, sql, tables_used, explanation, created_at, message_id(关联), embedding
---
四、Few-Shot LangGraph 集成
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 4.1 | 修改 State 定义 | easysql/llm/state.py | 添加 few_shot_examples 字段 |
| 4.2 | 新增检索节点 | easysql/llm/nodes/retrieve_few_shot.py | 从 Milvus 检索相似示例（按 db_name 过滤）|
| 4.3 | 修改 Agent 图 | easysql/llm/agent.py | 条件添加 retrieve_few_shot 节点 |
| 4.4 | 注册 FewShotSection | easysql/context/builder.py | 在 default() 中添加 |
---
五、Few-Shot API
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 5.1 | 新增 Few-Shot 路由 | easysql_api/routers/few_shot.py | 新建 |
| 5.2 | POST /few-shot | 同上 | 保存示例（关联 message_id）|
| 5.3 | GET /few-shot?db_name=xxx | 同上 | 列表（含关联的问题信息）|
| 5.4 | DELETE /few-shot/{id} | 同上 | 删除 |
| 5.5 | 修改 Session Detail API | easysql_api/routers/sessions.py | 返回消息时标记 is_few_shot |
| 5.6 | 注册路由 | easysql_api/app.py | 添加 few_shot_router |
---
六、前端 - 保存功能
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 6.1 | 添加"保存为示例"按钮 | components/Chat/SQLBlock.tsx | SQL 执行成功后显示 |
| 6.2 | Few-Shot API 客户端 | api/fewShot.ts | createFewShot(), getFewShots(), deleteFewShot() |
| 6.3 | 显示已保存标记 | components/Chat/MessageItem.tsx | 已保存的消息显示标签 |
---
七、前端 - Few-Shot 管理页面
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 7.1 | 新建管理页面 | pages/FewShot/index.tsx | 列表 + 删除 |
| 7.2 | 按数据库筛选 | 同上 | 下拉选择 db_name |
| 7.3 | 显示关联来源 | 同上 | 显示来自哪个 Session |
| 7.4 | 添加路由 | App.tsx | /few-shot |
| 7.5 | 添加导航菜单 | components/Layout/Sidebar.tsx | "示例管理" |
---
八、前端 - 历史会话标记
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 8.1 | 历史页面显示 few-shot 标记 | pages/History/index.tsx | 列表中标记哪些会话有 few-shot |
| 8.2 | 会话详情显示 few-shot 消息 | components/Layout/SessionList.tsx | 恢复时显示哪些消息是 few-shot |
---
九、国际化
| ID | 任务 | 文件 | 说明 |
|----|------|------|------|
| 9.1 | 中文翻译 | i18n/locales/zh.json | few-shot 相关 |
| 9.2 | 英文翻译 | i18n/locales/en.json | few-shot 相关 |
---
汇总
| 模块 | 任务数 | 预估工时 |
|------|--------|----------|
| Session 持久化 | 4 | 4h |
| Few-Shot 配置 | 1 | 0.5h |
| Few-Shot 存储 | 2 | 3h |
| LangGraph 集成 | 4 | 4h |
| Few-Shot API | 6 | 3h |
| 前端保存 | 3 | 2h |
| 前端管理页 | 5 | 4h |
| 历史会话标记 | 2 | 1.5h |
| 国际化 | 2 | 0.5h |
| 总计 | 29 | 22.5h |
---
是否开始实现？建议顺序：1 → 2 → 3 → 5 → 4 → 6 → 7 → 8 → 9