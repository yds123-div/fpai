# 领域模型与 API 适配器设计

## 1. 设计目标

- **一个接口对应一个领域模型**：如 [API接口-基金相关](./API接口-基金相关.md) 中的每个接口编码（0731H016、0731H017 等）对应一种业务数据类型，即一个可配置的领域模型。
- 系统需支持：
  1. **定义领域模型**及其**元数据**（Schema）；
  2. **定义数据获取方式**（如 HTTP REST API）：请求体参数、响应结构；
  3. **定义响应与领域模型元数据的映射**，解析结果后得到符合该模型的数据集。

原先「固定少数领域模型 + 每机构一个适配器类」的思路改为：**可配置的领域模型 + 可配置的元数据 + 可配置的数据源（含请求/响应/映射）**，新增接口时以配置为主，无需为每个接口写死适配器代码。

---

## 2. 统一领域模型（Domain Model）

### 2.1 概念

- **领域模型** = 一种业务数据的类型，由系统**配置定义**，而非在代码里写死类。
- 每个模型有唯一标识，建议与行内接口编码一致（如 `0731H016`），便于与 [API接口-基金相关](./API接口-基金相关.md) 一一对应。
- 属性：
  - **模型编码**（id/code）：如 `0731H016`、`0731H017`。
  - **名称**：如「基金基本信息查询」「基金行情查询」。
  - **描述**：可选，业务说明。
  - **元数据**：见下节，描述该模型的数据形状（字段列表、类型等）。

### 2.2 与接口的对应关系

| 接口编码   | 领域模型名称       | 说明     |
|-----------|--------------------|----------|
| 0731H016  | 基金基本信息       | 一接口一模型 |
| 0731H017  | 基金行情           | 同上     |
| 0731H018  | 基金指数           | 同上     |
| …         | …                  | 其余见 API接口-基金相关.md |

---

## 3. 元数据（Metadata）

### 3.1 作用

- 描述该领域模型的**数据结构**：有哪些字段、类型、是否必填等。
- 用于：校验、序列化、以及和「响应→模型」的**映射**配合，得到最终符合该模型的数据集。

### 3.2 元数据 Schema 定义

每个领域模型有一条**元数据**记录，包含**字段列表**。每个字段定义：

| 属性       | 类型     | 说明                         |
|------------|----------|------------------------------|
| name       | string   | 字段名（模型侧，最终数据集键名） |
| data_type  | enum     | string / number / boolean / date / array / object |
| required   | bool     | 是否必填                     |
| description| string   | 可选，字段说明               |
| default    | any      | 可选，默认值                 |
| source_path| string   | 可选，映射时从响应取值的路径（见 §5） |

### 3.3 示例（基金基本信息 0731H016）

```yaml
model_code: "0731H016"
model_name: "基金基本信息"
fields:
  - name: "fund_code"
    data_type: string
    required: true
    source_path: "$.fundCode"
  - name: "fund_name"
    data_type: string
    required: true
    source_path: "$.fundName"
  - name: "fund_type"
    data_type: string
    required: false
    source_path: "$.fundType"
  - name: "risk_level"
    data_type: string
    required: false
    source_path: "$.riskLevel"
```

---

## 4. 数据获取方式（Data Source）

### 4.1 概念

- 为每个领域模型配置**通过何种方式**获取数据。
- **类型**：先支持 **HTTP REST**；后续可扩展 gRPC、消息队列、文件等。
- 同一领域模型在不同机构/环境下可有**不同数据源绑定**（不同 base_url、不同 path/参数）。

### 4.2 数据源绑定

- **领域模型编码** → 绑定一个**数据源配置**（可按机构/租户再细分）。
- 数据源配置包含：
  - 类型：如 `http_rest`。
  - 连接信息：base_url、认证方式等。
  - **请求定义**：见 §4.3。
  - **响应定义**：见 §4.4。
  - **映射规则**：见 §5。

---

## 5. API 适配器（HTTP REST）配置

当数据获取方式为 **HTTP REST** 时，需完整定义请求、响应与映射。

### 5.1 请求定义（Request Spec）

| 属性       | 说明 |
|------------|------|
| method     | GET / POST / PUT 等 |
| path       | URL 路径，可含占位符，如 `/api/fund/{fundCode}` |
| query_params | 列表：name, in=query, data_type, required, default |
| body_params  | 列表：name, data_type, required, default（POST 等） |
| path_params  | 列表：name, 对应 path 中的占位符 |
| headers    | 可选，固定或参数化请求头 |

**请求体参数**即由上述 query_params / body_params / path_params 定义；调用统一接口时传入「参数名→值」的 map，由系统组装成实际请求。

### 5.2 响应定义（Response Spec）

描述**响应结构**，便于解析与映射：

| 属性           | 说明 |
|----------------|------|
| list_path      | 数据列表在响应中的路径，如 `data.list`、`result.items`（支持 JSON Path 或简单路径） |
| total_path     | 可选，总数在响应中的路径，如 `data.total` |
| single_path    | 可选，当接口只返回单条时，该条数据的路径，如 `data` |
| item_schema    | 可选，单条记录的预期结构说明（与映射配合） |

解析时：先按 `list_path`（或 `single_path`）取出「原始列表/单条」，再对每条应用**映射规则**得到领域模型数据。

### 5.3 映射规则（Response → 领域模型元数据）

- **目的**：把 API 响应的**原始结构**映射成符合**领域模型元数据**的数据集。
- **方式**：
  - 在元数据的每个字段上配置 **source_path**（如 `$.fundName`、`$.nested.price`），表示从「当前条」的哪一路径取值；
  - 或单独维护一份「响应路径 → 模型字段名」的映射表。
- 支持简单转换：类型转换（string→number、时间串→date）、默认值、取嵌套字段等。
- 映射后得到的是「符合该领域模型 Schema 的键值对列表」，即该领域模型的**真实数据集**。

### 5.4 端到端示例（0731H016 基金基本信息）

```yaml
# 数据源类型
data_source_type: http_rest

# 连接
base_url: "https://api.example.com"
auth: bearer_token  # 或 api_key / none

# 请求
request:
  method: POST
  path: "/v1/fund/basic"
  body_params:
    - name: "fundCode"
      data_type: string
      required: true
    - name: "includeDetail"
      data_type: boolean
      required: false
      default: false

# 响应
response:
  list_path: "$.data.list"      # 列表在此
  total_path: "$.data.total"    # 总数在此
  # 若为单条接口：single_path: "$.data"

# 映射（与元数据 source_path 一致，或在此集中写）
mapping:
  - model_field: "fund_code"
    response_path: "$.fundCode"
  - model_field: "fund_name"
    response_path: "$.fundName"
  - model_field: "risk_level"
    response_path: "$.riskLevel"
```

运行时：传入 `{ "fundCode": "000001" }` → 组装 POST body → 请求 → 从 `$.data.list` 取列表 → 对每条按 mapping 填 model_field → 得到 `[{ "fund_code": "000001", "fund_name": "...", "risk_level": "R2" }, ...]`。

---

## 6. 统一调用接口与运行时流程

### 6.1 统一接口

对上游（编排、智能体）暴露**单一语义**：

- **按领域模型获取数据**  
  `get_data(model_code, request_params, options?) → (records, total?)`  
  - `model_code`：领域模型编码（如 `0731H016`）。  
  - `request_params`：键值对，对应该模型所绑定的数据源的「请求定义」中的参数。  
  - `records`：符合该领域模型元数据的字典列表（或强类型实例）。  
  - `total`：若接口分页，则返回总数（从 response_spec.total_path 解析）。

可选扩展：

- `list_models() → List[DomainModelInfo]`：列出已配置的领域模型及其元数据摘要。  
- `get_model_metadata(model_code) → Metadata`：查询某模型的完整元数据。

### 6.2 运行时流程

1. **解析**：根据 `model_code` 找到领域模型及其绑定的数据源配置（含请求/响应/映射）。
2. **鉴权与路由**：按租户/机构选择对应数据源实例（如不同 base_url），注入权限上下文（如 userId、productPoolIds）。
3. **组装请求**：按请求定义 + `request_params` 生成 URL、query、body、headers。
4. **发送请求**：执行 HTTP 调用（含超时、重试、熔断）。
5. **解析响应**：按响应定义（list_path / total_path / single_path）从响应体中取出原始列表与总数。
6. **映射**：对每条原始记录，按映射规则（response_path → model_field）填到元数据定义的字段，得到符合该领域模型的数据集。
7. **返回**：返回 `(records, total?)`；可选做权限过滤、缓存（如按 model_code + params 做 key）。

---

## 7. 与现有实现的关系

- **现有 T010/T010a**：  
  - `ProductSummary`、`Quote`、`SalePermission` 等可视为**预置的领域模型**（有固定元数据与固定接口语义）。  
  - 现有「按机构选适配器」的 `get_products` / `get_quotes` / `check_sale_permission` 可保留为**便捷 API**，内部可转为对上述「按 model_code + 请求参数」的 `get_data` 的封装，或与新的「可配置领域模型」并存。
- **新增接口（如 0731H016～A0731H046）**：  
  - 每个接口配置为一个**领域模型**（编码 + 名称 + 元数据）+ 一个 **HTTP 数据源**（请求定义 + 响应定义 + 映射规则）。  
  - 新增接口时以**配置为主**（或配置 + 少量通用转换逻辑），无需为每个接口写一个适配器类。

---

## 8. 配置存储与扩展

- **领域模型与元数据**：可存 MySQL 表（如 `domain_models`、`domain_model_fields`）或配置文件/YAML，由 config 或 data_access 模块加载。
- **数据源与请求/响应/映射**：可存为 `data_sources`、`request_specs`、`response_specs`、`mapping_rules` 等表或 YAML，按 model_code（及可选 org_id）关联。
- **扩展**：  
  - 增加数据源类型（如 gRPC）时，增加对应「请求/响应/映射」的配置形态与执行器。  
  - 映射层可支持简单脚本或表达式，用于复杂转换（如单位换算、枚举映射）。

---

## 9. 小结

| 概念           | 说明 |
|----------------|------|
| **领域模型**   | 可配置的业务数据类型，一接口一模型；含模型编码、名称、描述。 |
| **元数据**     | 模型的 Schema：字段名、类型、必填、默认值、source_path（映射用）。 |
| **数据获取方式** | 如何取数：先支持 HTTP REST；含 base_url、认证等。 |
| **请求定义**   | 方法、path、query/body/path 参数列表。 |
| **响应定义**   | list_path、total_path、single_path，描述响应结构。 |
| **映射规则**   | 响应路径 → 模型字段，解析后得到符合元数据的数据集。 |
| **统一接口**   | `get_data(model_code, request_params)` → (records, total?)。 |

该设计使「一个接口 = 一个领域模型」，通过**定义领域模型、元数据、请求/响应与映射**，用配置驱动数据获取与标准化，减少为每个接口写死适配器的需求。
