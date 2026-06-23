# FPAI 项目 CloudBase 部署计划

## Context

项目已在本地 Docker 成功运行，现部署到腾讯云开发 (CloudBase)。
- CloudBase 环境: `ceshi-d2ge61l3r9423468d`
- 数据源: 本地 MySQL `127.0.0.1:3306` / `fpai` 库 (20 张表，5 张有数据)
- 远程 Milvus/MinIO 不可用，全部在 CloudBase 上自建

## CloudBase 架构 (4 个服务)

```
CloudBase 环境: ceshi-d2ge61l3r9423468d
├── MySQL (CloudBase 托管)          ← manageSqlDatabase
├── MinIO (CloudRun 容器)           ← minio/minio, 端口 9000
├── Milvus (CloudRun 容器)          ← milvusdb/milvus standalone, 端口 19530
└── fpai (CloudRun 容器)            ← nginx:80 + uvicorn:8000 合并容器
       ▲
       │  https://fpai-<env-id>.webapps.tcloudbase.com
       │  同源访问 (Nginx 反向代理 127.0.0.1:8000)
```

所有服务通过 CloudRun 内部网络互相通信。

## 实施步骤

### Phase 0: 环境准备
1. CloudBase 认证: `auth(action=start_auth)`
2. 查询环境: `envQuery(action=list)`
3. 检查已有资源: `queryCloudRun(action=list)`

### Phase 1: 数据导出
从本地 MySQL `127.0.0.1:3306` 导出:
```bash
mysqldump -h 127.0.0.1 -P 3306 -u root -p"k2q3#k5f" \
  --no-create-info --complete-insert fpai \
  users roles user_roles menus role_menus > data_migration.sql
```
同时导出完整表结构:
```bash
mysqldump -h 127.0.0.1 -P 3306 -u root -p"k2q3#k5f" \
  --no-data fpai > schema.sql
```

### Phase 2: 创建 CloudBase MySQL
1. `manageSqlDatabase` 创建 MySQL 实例
2. 执行建表 SQL（从 schema.sql 或 bootstrap_local_db.py 的 BOOTSTRAP_SQL）
3. 导入 data_migration.sql 恢复 RBAC 数据 (admin 账号/角色/菜单)
4. 记录连接信息 (host/port/user/password)

### Phase 3: 部署 MinIO (CloudRun 容器)
`manageCloudRun` action=deploy:
- serverName: `fpai-minio`
- serverType: container
- Dockerfile 直接用官方镜像 `minio/minio:latest`
- Port: 9000
- OpenAccessTypes: ["PUBLIC"]
- EnvParams: `MINIO_ROOT_USER=admin`, `MINIO_ROOT_PASSWORD=k2q3#k5f`
- Cmd: `["server", "/data", "--console-address", ":9001"]`
- MinNum: 1

### Phase 4: 部署 Milvus (CloudRun 容器)
`manageCloudRun` action=deploy:
- serverName: `fpai-milvus`
- serverType: container
- Dockerfile 用 `milvusdb/milvus:v2.4.0` 镜像
- Port: 19530
- OpenAccessTypes: ["PUBLIC"]
- Cmd: `["milvus", "run", "standalone"]`
- MinNum: 1

### Phase 5: 构建 & 部署 fpai 合并容器
创建 3 个新文件:

**`Dockerfile.cloudrun`** — 多阶段构建:
- Stage 1: node:20-alpine 构建前端 → dist/
- Stage 2: python:3.11-slim-bookworm + nginx + supervisor
  - 安装 nginx、supervisor、curl
  - pip install Python deps
  - COPY backend 源码 + frontend dist + nginx 配置 + supervisor 配置
  - EXPOSE 80

**`nginx.cloudrun.conf`** — 基于 frontend/nginx.conf:
- `proxy_pass http://backend:8000` → `proxy_pass http://127.0.0.1:8000`

**`supervisord.conf`** — 管理 nginx + uvicorn

`manageCloudRun` action=deploy:
- serverName: `fpai`
- targetPath: D:\project\fpai (项目根目录)
- serverType: container
- Dockerfile: `Dockerfile.cloudrun`
- Port: 80
- OpenAccessTypes: ["PUBLIC"]
- Cpu: 1, Mem: 2, MinNum: 1
- EnvParams (关键配置):
  ```
  MYSQL_HOST=<CloudBase MySQL host>
  MYSQL_PORT=<CloudBase MySQL port>
  MYSQL_USER=root, MYSQL_PASSWORD=..., MYSQL_DATABASE=fpai
  MINIO_ENDPOINT=<fpai-minio 内部地址>:9000
  MINIO_ACCESS_KEY=admin, MINIO_SECRET_KEY=k2q3#k5f
  MILVUS_HOST=<fpai-milvus 内部地址>
  MILVUS_PORT=19530
  LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
  LLM_API_KEY=..., LLM_MODEL=deepseek-v4-flash-260425
  EMBEDDING_BASE_URL=..., EMBEDDING_API_KEY=..., EMBEDDING_MODEL=...
  RERANKER_BASE_URL=..., RERANKER_API_KEY=..., RERANKER_MODEL=...
  JWT_SECRET=<至少 32 字符>
  EXTERNAL_KB_BASE_URL=..., EXTERNAL_KB_API_KEY=...
  ```

### Phase 6: 验证
1. `curl https://fpai-<env>.webapps.tcloudbase.com/health` → `{"status":"ok"}`
2. 浏览器访问，用 admin/admin123 登录
3. 验证菜单/角色正常 (数据迁移成功)
4. 验证文档上传 (MinIO) 和知识检索 (Milvus) 可用

## 需创建的文件

| 文件 | 说明 |
|------|------|
| `Dockerfile.cloudrun` | 合并前端+后端+nginx+supervisord |
| `nginx.cloudrun.conf` | 代理目标改为 127.0.0.1:8000 |
| `supervisord.conf` | 管理 nginx + uvicorn 双进程 |

## 需部署的 CloudBase 服务

| 服务名 | 类型 | 端口 | 说明 |
|--------|------|------|------|
| MySQL | 托管数据库 | 3306 | CloudBase 托管 MySQL |
| fpai-minio | CloudRun 容器 | 9000 | 对象存储 |
| fpai-milvus | CloudRun 容器 | 19530 | 向量数据库 |
| fpai | CloudRun 容器 | 80 | 主应用 (nginx + FastAPI) |

## 数据迁移范围

| 表 | 行数 | 说明 |
|----|------|------|
| users | 1 | admin 用户 (密码 admin123) |
| roles | 1 | 管理员角色 |
| user_roles | 1 | admin→管理员 |
| menus | 9 | 菜单项 |
| role_menus | 9 | 角色→菜单绑定 |
