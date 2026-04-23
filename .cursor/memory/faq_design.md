# FAQ 智能体方案设计（向量化 + TopK 检索 + LLM 回答）

<!-- 依据用户指定流程：FAQ 入库 → MySQL → 同步 → Embedding → 向量库 → 检索 TopK → LLM 回答 -->

## 流程概览

```
     FAQ 数据入库
            │
 ┌───────────────┐
 │ 结构化数据库  │  (MySQL faq 表)
 └───────────────┘
            │
            │ 同步
            ▼
    Embedding 模型
            │
            ▼
    向量数据库 (Milvus)
            │
            ▼
         检索层
   (TopK 相似 FAQ)
            │
            ▼
        LLM 回答
```

## 1. FAQ 入库（已有）

- **数据源**：MySQL 表 `faq`（T004 迁移 001），字段：id、question、answer、tags、effective_from、effective_to。
- **入库方式**：业务侧 INSERT/UPDATE；仅生效期内（effective_from ≤ now ≤ effective_to 或均为 NULL）的条目参与同步与检索。

## 2. 同步：MySQL → Embedding → Milvus

| 步骤 | 说明 |
|------|------|
| 读取 | 从 MySQL 读取所有在生效期内的 FAQ（id, question, answer）。 |
| 向量化 | 使用 model_gateway.embed 对 **question** 做向量化（与检索时 query 向量同模型）。 |
| 写入 | 写入 Milvus 专用 Collection（如 `fpai_faq`），Schema 与现有 chunk 一致以便复用：id=`faq_{id}`、vector、doc_id=`{id}`、source=`faq`、chunk_text=question；answer 不落向量库，检索后按 doc_id 回表 MySQL 取 answer。 |
| 策略 | 全量同步：先按 source=faq 删除旧向量（或使用独立 Collection 则全量覆盖），再批量 insert 当前生效 FAQ。 |

## 3. 检索层（TopK 相似 FAQ）

- **输入**：用户 query 字符串。
- **步骤**：query → embed([query]) → Milvus 向量检索（Collection fpai_faq，TopK）→ 得到 doc_id 列表（即 faq id）→ 按 id 从 MySQL 取完整 FAQ（question、answer）→ 返回 `list[FAQHit]`。
- **输出**：按相似度排序的 TopK 条 FAQ（含 question、answer、id），供 LLM 使用。

## 4. LLM 回答

- **输入**：用户 question + TopK 条 FAQ（每条 question + answer）。
- **步骤**：将「用户问题」与「检索到的 FAQ 列表」拼成 prompt，调用 model_gateway.llm_chat，让 LLM 基于标准答生成自然、贴合问题的最终回答；可要求引用来源（citations）。
- **输出**：answer_blocks、citations（来自 FAQ 的 question/answer/id）。

## 5. 任务编排建议

| 子项 | 描述 | 依赖 |
|------|------|------|
| T016.1 | FAQ 同步：从 MySQL 读取生效 FAQ → Embedding → 写入 Milvus（fpai_faq 或带 source=faq 的 collection） | T004, T008 |
| T016.2 | FAQ 检索层：query → embed → Milvus TopK → 回表 MySQL 取 answer → 返回 FAQHit 列表 | T016.1, T008 |
| T016.3 | FAQ 回答：检索 TopK + LLM 基于 FAQ 生成回答；对外 query_faq(question)，由 Coordinator 编排路由调用 | T016.2, T008 |

以上三部分可在 tasks.md 中合并为 T016 一条，或拆为 T016a/T016b/T016c；实现时保持「入库 → 同步 → 向量检索 → LLM 回答」一条链。

## 6. 与现有组件的复用

- **Embedding**：model_gateway.embed（与 retrieval 一致）。
- **Milvus**：pkg.milvus_client（ensure_collection、insert_chunks、search_with_filter）；FAQ 使用独立 collection 名 `fpai_faq` 或通过 source=faq 过滤，避免与 RAG chunk 混用。
- **LLM**：model_gateway.llm_chat。
- **MySQL**：pkg.mysql_client；faq 表已存在。
