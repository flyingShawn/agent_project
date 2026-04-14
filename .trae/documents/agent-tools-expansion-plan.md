# Agent 工具扩展调研分析与实施计划

## 一、现状分析

### 当前工具清单（3个）

| 工具名 | 类别 | 核心能力 |
|--------|------|----------|
| `sql_query` | 数据库查询 | NL→SQL生成 + 安全校验 + 执行 + Markdown表格 |
| `rag_search` | 知识库检索 | 向量+BM25混合检索 + 文档片段+来源 |
| `metadata_query` | 元数据查询 | 表结构/字段/关联/同义词查询 |

### 核心架构

- 基于 **LangGraph StateGraph** 编排，LLM 通过 Tool Calling 自主决策
- 工具注册中心：`agent/tools/__init__.py` → `ALL_TOOLS` 列表
- 工具定义规范：`@tool(args_schema=PydanticModel)` 装饰器
- 系统提示词：`agent/prompts.py` → `SYSTEM_PROMPT`
- 状态管理：`agent/state.py` → `AgentState` TypedDict
- 最大工具调用次数：5次

### 关键缺陷

当前工具体系**全部是"信息获取"型工具**，缺乏：
1. **环境感知**：LLM 不知道当前时间，导致日期相关查询永远出错
2. **精确计算**：LLM 数学计算不可靠，在线率、环比等计算容易出错
3. **数据可视化**：只能返回文本/表格，无法生成图表
4. **数据导出**：用户无法下载查询结果
5. **外部信息**：无法获取知识库和数据库之外的信息

---

## 二、工具扩展调研分析

### 2.1 时间工具 (Time Tool) — ⭐⭐⭐⭐⭐ 必须实现

**问题痛点**：
- 用户问"今天有多少台设备在线"，LLM 不知道当前日期，生成的 SQL 中 `WHERE` 条件的日期永远不对
- 用户问"本月告警数量"、"最近7天在线率"，LLM 无法计算正确的日期范围
- 这是**最高频、最致命**的问题，直接影响核心查询场景的准确性

**工具设计**：
```python
class TimeToolInput(BaseModel):
    format: str | None = Field(default=None, description="日期格式，默认返回完整信息")

@tool(args_schema=TimeToolInput)
def get_current_time(format: str | None = None) -> str:
    """
    获取当前日期和时间信息。
    当用户问题涉及"今天"、"本月"、"最近N天"、"本周"、"今年"等时间相关表述时，
    必须先调用此工具获取准确时间，再基于返回结果生成SQL查询。
    """
    # 返回：当前日期、星期几、本月起止、本年起止、最近N天的日期范围等
```

**返回内容示例**：
```json
{
  "current_date": "2026-04-14",
  "current_datetime": "2026-04-14 10:30:00",
  "day_of_week": "星期二",
  "today_start": "2026-04-14 00:00:00",
  "today_end": "2026-04-14 23:59:59",
  "this_month_start": "2026-04-01",
  "this_month_end": "2026-04-30",
  "this_year_start": "2026-01-01",
  "this_year_end": "2026-12-31",
  "recent_7_days_start": "2026-04-08",
  "recent_30_days_start": "2026-03-15"
}
```

**实现复杂度**：⭐ 极低（纯 Python datetime，无外部依赖）

---

### 2.2 计算工具 (Calculator Tool) — ⭐⭐⭐⭐ 强烈推荐

**问题痛点**：
- 用户问"在线率是多少"，SQL 返回在线数和总数，但 LLM 做除法容易出错（如 156/890 = ?）
- 用户问"告警环比增长了多少"，需要两个月数据做差再除以上月，LLM 计算不可靠
- LLM 的数学能力是已知弱点，尤其是百分比、比率、差值计算

**工具设计**：
```python
class CalculatorInput(BaseModel):
    expression: str = Field(description="数学表达式，如 '156/890*100' 或 'round((234-189)/189*100, 2)'")

@tool(args_schema=CalculatorInput)
def calculator(expression: str) -> str:
    """
    执行数学计算。
    当需要计算百分比、比率、差值、环比、同比等数值运算时使用此工具。
    支持基本算术运算、百分比计算、四舍五入等。
    """
```

**安全考虑**：
- 不使用 `eval()`，使用 `ast.literal_eval` 或安全的数学表达式解析器
- 仅允许数字、运算符（+-*/%）、括号、round/abs/min/max 函数
- 禁止任何变量赋值、函数定义、模块导入

**实现复杂度**：⭐⭐ 低（安全表达式解析器约50行代码）

---

### 2.3 图表生成工具 (Chart Tool) — ⭐⭐⭐⭐ 强烈推荐

**问题痛点**：
- 用户问"各部门设备数量对比"，只能看到文本表格，无法直观感受差异
- 用户问"告警趋势"，表格无法展示时间序列变化
- 数据可视化是管理系统的核心需求，纯文本回答体验差

**工具设计**：
```python
class ChartInput(BaseModel):
    chart_type: str = Field(description="图表类型：bar/line/pie/table")
    title: str = Field(description="图表标题")
    data: str = Field(description="JSON格式的数据，包含columns和rows")
    x_field: str | None = Field(default=None, description="X轴字段名")
    y_field: str | None = Field(default=None, description="Y轴字段名")

@tool(args_schema=ChartInput)
def generate_chart(chart_type: str, title: str, data: str,
                   x_field: str | None = None, y_field: str | None = None) -> str:
    """
    根据数据生成图表。
    当用户需要可视化展示数据对比、趋势、占比时使用此工具。
    支持柱状图(bar)、折线图(line)、饼图(pie)。
    """
```

**技术方案**：
- 方案A：后端用 matplotlib/pyecharts 生成图片，返回 base64
- 方案B：返回 ECharts 配置 JSON，前端渲染（推荐，交互性更好）

**实现复杂度**：⭐⭐⭐ 中等（需要前后端配合）

---

### 2.4 数据导出工具 (Export Tool) — ⭐⭐⭐ 推荐

**问题痛点**：
- 用户查询到数据后，经常需要导出为 Excel/CSV 进行二次分析或汇报
- 当前只能在前端手动复制表格数据，体验差

**工具设计**：
```python
class ExportInput(BaseModel):
    data: str = Field(description="JSON格式的数据，包含columns和rows")
    filename: str = Field(default="export", description="导出文件名")
    format: str = Field(default="xlsx", description="导出格式：xlsx/csv")

@tool(args_schema=ExportInput)
def export_data(data: str, filename: str = "export", format: str = "xlsx") -> str:
    """
    将数据导出为Excel或CSV文件。
    当用户要求导出、下载、保存查询结果时使用此工具。
    """
```

**技术方案**：
- 后端生成文件，存入临时目录，返回下载链接
- 前端展示下载链接，用户点击下载

**实现复杂度**：⭐⭐⭐ 中等（需要文件管理、下载接口、清理机制）

---

### 2.5 网络搜索工具 (Web Search Tool) — ⭐⭐⭐ 推荐

**问题痛点**：
- 用户问"Windows 11最新版本号是什么"，内部知识库可能没有
- 用户问"xxx错误码怎么解决"，可能需要搜索互联网
- 内部知识库覆盖面有限，外部信息是重要补充

**工具设计**：
```python
class WebSearchInput(BaseModel):
    query: str = Field(description="搜索关键词")

@tool(args_schema=WebSearchInput)
def web_search(query: str) -> str:
    """
    搜索互联网获取信息。
    当用户问题涉及外部知识、最新资讯、错误码查询等
    内部知识库无法覆盖的内容时使用此工具。
    """
```

**技术方案**：
- 调用搜索引擎 API（如 Bing Search API、SerpAPI）
- 或使用 Tavily Search（LangChain 生态推荐）

**实现复杂度**：⭐⭐⭐ 中等（需要外部 API 依赖和配置）

---

### 2.6 其他候选工具（暂不实施，供后续参考）

| 工具 | 价值 | 暂不实施原因 |
|------|------|-------------|
| 设备操作工具 | 高 | 安全风险大，需要严格的权限控制和审批流程 |
| 代码执行工具 | 中 | 安全风险极高，沙箱隔离复杂 |
| 文件分析工具 | 中 | 已有 images_base64 支持图片，优先级较低 |
| 邮件通知工具 | 低 | 使用场景有限，非核心需求 |
| 定时任务工具 | 低 | 架构变更大，需独立调度系统 |

---

## 三、最终决策：新增工具清单

### 第一批实施（本次计划）

| 优先级 | 工具名 | 工具函数名 | 核心价值 |
|--------|--------|-----------|---------|
| P0 | 时间工具 | `get_current_time` | 解决日期查询永远出错的致命问题 |
| P1 | 计算工具 | `calculator` | 解决 LLM 数学计算不可靠的问题 |
| P1 | 图表生成工具 | `generate_chart` | 数据可视化，提升用户体验 |
| P2 | 数据导出工具 | `export_data` | 数据导出下载，实用功能 |
| P2 | 网络搜索工具 | `web_search` | 扩展信息获取范围 |

### 优先级说明

- **P0（必须实现）**：时间工具 — 直接影响核心查询场景准确性，用户已明确反馈
- **P1（强烈推荐）**：计算工具、图表工具 — 高频需求，显著提升回答质量
- **P2（推荐实现）**：导出工具、搜索工具 — 实用功能，锦上添花

---

## 四、实施步骤

### Step 1：创建时间工具 `get_current_time`

**新增文件**：`agent_backend/agent/tools/time_tool.py`

1. 定义 `TimeToolInput` Pydantic 模型
2. 实现 `get_current_time` 函数，返回当前日期、时间、星期、常用日期范围
3. 在 `agent/tools/__init__.py` 中注册到 `ALL_TOOLS`
4. 在 `agent/prompts.py` 的 `SYSTEM_PROMPT` 中添加时间工具说明
5. 在 `agent/state.py` 的 `AgentState` 中添加 `time_results` 字段（可选）

### Step 2：创建计算工具 `calculator`

**新增文件**：`agent_backend/agent/tools/calculator_tool.py`

1. 实现安全的数学表达式解析器（基于 `ast` 模块，白名单机制）
2. 定义 `CalculatorInput` Pydantic 模型
3. 实现 `calculator` 函数
4. 注册到 `ALL_TOOLS`
5. 更新 `SYSTEM_PROMPT`

### Step 3：创建图表生成工具 `generate_chart`

**新增文件**：`agent_backend/agent/tools/chart_tool.py`

1. 定义 `ChartInput` Pydantic 模型
2. 实现 `generate_chart` 函数，生成 ECharts 配置 JSON
3. 注册到 `ALL_TOOLS`
4. 更新 `SYSTEM_PROMPT`
5. 前端添加 ECharts 渲染组件（需配合前端修改）
6. 在 `agent/state.py` 中添加 `chart_configs` 字段
7. 在 `stream.py` 中添加 `chart` SSE 事件类型

### Step 4：创建数据导出工具 `export_data`

**新增文件**：`agent_backend/agent/tools/export_tool.py`

1. 定义 `ExportInput` Pydantic 模型
2. 实现 `export_data` 函数，生成 Excel/CSV 文件
3. 添加文件下载 API 端点
4. 注册到 `ALL_TOOLS`
5. 更新 `SYSTEM_PROMPT`

### Step 5：创建网络搜索工具 `web_search`

**新增文件**：`agent_backend/agent/tools/web_search_tool.py`

1. 定义 `WebSearchInput` Pydantic 模型
2. 实现搜索功能（可配置搜索引擎后端）
3. 注册到 `ALL_TOOLS`
4. 更新 `SYSTEM_PROMPT`
5. 添加相关环境变量配置

### Step 6：更新系统提示词和状态管理

1. 更新 `SYSTEM_PROMPT`，添加所有新工具的说明和决策规则
2. 更新 `AgentState`，添加新工具的结果字段
3. 更新 `tool_result_node`，处理新工具的结果收集
4. 更新 `stream.py`，添加新工具的 SSE 事件类型

### Step 7：测试验证

1. 编写各工具的单元测试
2. 端到端测试：验证 LLM 能正确选择和调用新工具
3. 重点验证时间工具：确保"今日数据"查询日期正确

---

## 五、技术规范

### 工具定义规范（遵循现有模式）

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class XxxInput(BaseModel):
    """工具入参模型"""
    param: str = Field(description="参数说明")

@tool(args_schema=XxxInput)
def tool_name(param: str) -> str:
    """
    工具描述（LLM 根据此描述决策是否调用）。
    详细说明适用场景和示例问题。

    参数：
        param: 参数说明

    返回：
        str: 返回值说明
    """
    # 实现
```

### 注册规范

1. 在 `agent/tools/__init__.py` 中导入并添加到 `ALL_TOOLS`
2. 在 `agent/prompts.py` 的 `SYSTEM_PROMPT` 中添加工具说明
3. 在 `agent/state.py` 中添加结果累积字段（如需要）
4. 在 `agent/nodes.py` 的 `tool_result_node` 中添加结果收集逻辑（如需要）

### 安全规范

1. 所有工具返回 `str` 类型（JSON 字符串或纯文本）
2. 工具内部捕获所有异常，返回错误信息而非抛出异常
3. 计算工具使用白名单机制，禁止任意代码执行
4. 搜索工具需要配置项控制是否启用
5. 导出工具需要文件大小限制和自动清理机制
