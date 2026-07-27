# 金融产品解析智能体 - 后端

一期全 Python 模块化单体，与 `.cursor/memory/project_context.md`、`technical_design.md` 一致。

## 环境

- Python 3.12+（代码含 PEP 701 嵌套引号 f-string，agentscope 2.0 亦要求 >=3.11）
- 依赖：`pip install -r requirements.txt` 或 `pip install -e .`

## 启动

```bash
# 在 backend 目录下
uvicorn api.main:app --reload
```

- 健康检查：`GET /health`
- API 根：`GET /api/v1`

## 环境变量

复制 `.env.example` 为 `.env` 并填写实际值（DB、Redis、Milvus、MinIO、模型地址等）。勿提交 `.env`。
