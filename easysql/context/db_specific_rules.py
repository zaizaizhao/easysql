"""
Database-specific SQL syntax rules.

Provides rules and constraints specific to each database type to help
LLM generate syntactically correct SQL for the target database.
"""

from typing import Literal

DatabaseType = Literal["mysql", "postgresql", "oracle", "sqlserver"]


# Database-specific rules for SQL generation
DB_RULES: dict[str, str] = {
    "postgresql": """
### PostgreSQL 特定规则
1. **日期/时间运算**: PostgreSQL 的日期减法返回 INTERVAL 类型，不能直接与整数比较
   - 错误: `date1 - date2 > 7`
   - 正确: `date1 - date2 > INTERVAL '7 days'` 或 `EXTRACT(DAY FROM date1 - date2) > 7`
2. **字符串连接**: 使用 `||` 或 `CONCAT()` 函数
3. **布尔类型**: 支持原生 BOOLEAN，使用 TRUE/FALSE
4. **LIMIT 语法**: `LIMIT n OFFSET m`
5. **大小写敏感**: 标识符默认小写，用双引号保留大小写 `"TableName"`
6. **JSON操作**: 使用 `->` (JSON对象) 和 `->>` (文本)
7. **数组支持**: 支持原生数组类型，如 `integer[]`
8. **序列**: 使用 SERIAL/BIGSERIAL 或 IDENTITY
""",
    "mysql": """
### MySQL 特定规则
1. **日期运算**: 使用 `DATEDIFF(date1, date2)` 返回天数差
   - 错误: `date1 - date2 > 7`
   - 正确: `DATEDIFF(date1, date2) > 7`
2. **字符串连接**: 使用 `CONCAT()` 函数，`||` 默认是 OR 运算符
3. **布尔类型**: 使用 TINYINT(1)，0=FALSE, 1=TRUE
4. **LIMIT 语法**: `LIMIT m, n` 或 `LIMIT n OFFSET m`
5. **大小写敏感**: 取决于操作系统和排序规则
6. **反引号**: 使用反引号 `` ` `` 包裹标识符
7. **GROUP BY**: 默认必须包含所有非聚合列
8. **AUTO_INCREMENT**: 使用 AUTO_INCREMENT 而非 SERIAL
""",
    "oracle": """
### Oracle 特定规则
1. **日期运算**: 日期减法返回天数（数值），可直接与整数比较
   - `date1 - date2 > 7` 是正确的
2. **字符串连接**: 使用 `||` 运算符
3. **NULL 与空字符串**: Oracle 将空字符串视为 NULL
4. **分页查询**: 使用 ROWNUM 或 FETCH FIRST n ROWS ONLY (12c+)
   - `WHERE ROWNUM <= 10`
   - `FETCH FIRST 10 ROWS ONLY`
5. **FROM 子句**: SELECT 必须有 FROM 子句，单值查询使用 `FROM DUAL`
6. **双引号**: 用于保留大小写的标识符
7. **序列**: 使用 `sequence_name.NEXTVAL` 和 `sequence_name.CURRVAL`
8. **数据类型**: 使用 VARCHAR2, NUMBER, DATE, CLOB
""",
    "sqlserver": """
### SQL Server 特定规则
1. **日期运算**: 使用 `DATEDIFF(day, date1, date2)` 函数
   - 错误: `date1 - date2 > 7`
   - 正确: `DATEDIFF(day, date1, date2) > 7`
2. **字符串连接**: 使用 `+` 运算符或 `CONCAT()`
3. **TOP 语法**: 使用 `TOP n` 而非 LIMIT
   - `SELECT TOP 10 * FROM table`
4. **分页**: 使用 `OFFSET m ROWS FETCH NEXT n ROWS ONLY`
5. **方括号**: 使用 `[identifier]` 包裹标识符
6. **布尔类型**: 使用 BIT (0/1)
7. **IDENTITY**: 使用 IDENTITY(1,1) 自增
8. **NOLOCK**: 可使用 `WITH (NOLOCK)` 提示
""",
}


def get_db_specific_rules(db_type: str | None) -> str:
    """
    Get database-specific SQL syntax rules.

    Args:
        db_type: Database type (mysql, postgresql, oracle, sqlserver).
                 If None or unknown, returns empty string.

    Returns:
        Database-specific rules as a formatted string.
    """
    if not db_type:
        return ""

    db_type_lower = db_type.lower()
    return DB_RULES.get(db_type_lower, "")


def get_db_type_from_config(db_name: str | None = None) -> str | None:
    """
    Get database type from configuration.

    Args:
        db_name: Database configuration name. If None, uses first configured database.

    Returns:
        Database type string or None if not found.
    """
    from easysql.config import get_settings

    settings = get_settings()
    databases = settings.databases

    if not databases:
        return None

    if db_name:
        db_config = databases.get(db_name.lower())
        if db_config:
            return db_config.db_type
        return None

    # Return first database's type if no specific name given
    first_db = next(iter(databases.values()), None)
    return first_db.db_type if first_db else None
