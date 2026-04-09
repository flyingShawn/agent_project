# 配置文件合并计划

## 1. 仓库研究结论

### 1.1 配置文件现状

- **schema_metadata.yaml**：
  - 位于 `agent_backend/configs/schema_metadata.yaml`
  - 包含数据库表结构、字段信息、关系、权限规则、查询模式、显示字段等
  - 被多个模块使用：config_loader.py、permission_wrapper.py、patterns.py、metadata.py等
  - 是系统的核心配置文件

- **prompt_config.yaml**：
  - 位于 `agent_backend/configs/prompt_config.yaml`
  - 主要用于配置AI查询SQL及展示、总结应该使用的字段
  - 包含department、machine、hardware三个部分的字段配置
  - 包含required_fields部分，定义了必须的字段
  - 只被handlers.py文件使用

### 1.2 合并可行性分析

- 两个文件都包含了字段配置信息，但schema_metadata.yaml更全面
- prompt_config.yaml的字段配置可以合并到schema_metadata.yaml的display_fields部分
- required_fields可以作为一个新的顶层字段添加到schema_metadata.yaml中
- 合并后可以减少配置文件数量，提高维护性

## 2. 实施步骤

### 2.1 合并配置文件

1. **更新schema_metadata.yaml**：
   - 在display_fields部分添加prompt_config.yaml中的字段配置
   - 添加required_fields顶层字段
   - 保持原有功能不变

### 2.2 修改handlers.py

1. **更新配置文件路径**：
   - 将prompt_config.yaml的读取路径改为合并后的配置文件

2. **更新配置读取逻辑**：
   - 修改读取逻辑，从合并后的配置文件中获取字段配置
   - 保持原有功能不变

### 2.3 删除prompt_config.yaml

1. **删除文件**：
   - 确认所有使用prompt_config.yaml的地方都已更新后，删除该文件

### 2.4 更新文件名

1. **重命名schema_metadata.yaml**：
   - 选择一个更简洁的新文件名
   - 建议的文件名：
     - `metadata_config.yaml` - 简洁明了，反映其元数据配置的作用
     - `system_config.yaml` - 强调其作为系统核心配置的地位
     - `app_config.yaml` - 通用的应用配置文件名
     - `core_config.yaml` - 强调其作为核心配置的作用

2. **更新所有引用**：
   - 搜索并更新所有使用schema_metadata.yaml的地方，将其改为新的文件名
   - 包括代码文件、配置文件、文档等

## 3. 潜在依赖和考虑因素

### 3.1 依赖关系

- **config_loader.py**：负责加载和解析配置文件，需要更新文件路径
- **handlers.py**：使用prompt_config.yaml，需要更新配置读取逻辑
- **其他模块**：如permission_wrapper.py、patterns.py、metadata.py等，需要更新文件路径

### 3.2 风险处理

- **兼容性风险**：确保合并后的配置文件保持原有功能不变
- **路径更新风险**：确保所有引用都被正确更新
- **测试风险**：合并后需要进行充分的测试，确保系统正常运行

## 4. 具体实施计划

### 4.1 步骤一：合并配置文件

1. 打开schema_metadata.yaml文件
2. 在display_fields部分添加prompt_config.yaml中的字段配置
3. 在顶层添加required_fields字段
4. 保存文件

### 4.2 步骤二：修改handlers.py

1. 打开handlers.py文件
2. 更新配置文件路径为合并后的配置文件路径
3. 修改配置读取逻辑，从合并后的配置文件中获取字段配置
4. 保存文件

### 4.3 步骤三：删除prompt_config.yaml

1. 确认所有使用prompt_config.yaml的地方都已更新
2. 删除prompt_config.yaml文件

### 4.4 步骤四：更新文件名

1. 选择新的文件名
2. 重命名schema_metadata.yaml为新的文件名
3. 搜索并更新所有使用schema_metadata.yaml的地方，将其改为新的文件名
4. 保存所有修改的文件

### 4.5 步骤五：测试验证

1. 运行系统，确保所有功能正常
2. 测试AI查询功能，确保字段配置正确
3. 测试权限功能，确保权限规则正常
4. 测试其他依赖配置文件的功能，确保正常运行

## 5. 结论

合并prompt_config.yaml到schema_metadata.yaml并更新文件名为更简洁的名称，将有助于减少配置文件数量，提高维护性，同时保持系统功能不变。实施过程中需要注意更新所有引用，确保系统正常运行。