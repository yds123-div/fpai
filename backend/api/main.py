"""
FastAPI 应用入口（占位）。

从 backend 目录启动：
  uvicorn api.main:app --reload --port 8000
或（端口可由环境变量 PORT 指定）：
  python -m api.main
"""
from pathlib import Path

from dotenv import load_dotenv

# 最先加载 .env，使 MYSQL_*、LOG_LEVEL、PORT 等环境变量生效
# 优先加载 backend/.env（按 main.py 所在目录推算），再加载当前工作目录 .env
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env")
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.middleware import add_trace_id_middleware, add_auth_middleware
from api.routes import auth as auth_routes
from api.routes import users as users_routes
from api.routes import chat as chat_routes
from api.routes import compare_recommend_report as compare_recommend_report_routes
from api.routes import evidence_feedback_products_sessions as evidence_feedback_products_sessions_routes
from api.routes import documents as documents_routes
from api.routes import knowledge as knowledge_routes
from api.routes import models as models_routes
from api.routes import agents as agents_routes
from api.routes import rbac as rbac_routes
from api.routes import skills as skills_routes
from api.routes import config as config_routes
from api.routes import funds as funds_routes
from api.routes import fund_ratings as fund_ratings_routes
from pkg.codes import ErrorCode, envelope, message_for
from pkg.logger import configure_logging, get_logger

# 启动时配置日志：输出到控制台，级别由环境变量 LOG_LEVEL 控制（默认 INFO；DEBUG 可看到 auth 等详细日志）
configure_logging()

_log = get_logger(__name__)

app = FastAPI(
    title="金融产品解析智能体 API",
    description="财富业务全场景智能问答与辅助决策",
    version="0.1.0",
)

app.middleware("http")(add_trace_id_middleware)
app.middleware("http")(add_auth_middleware)


def _envelope_response(code: ErrorCode, message: str | None = None, data: dict | list | None = None):
    return JSONResponse(
        status_code=200,
        content=envelope(code=code, message=message, data=data),
    )


def _http_status_to_error_code(status_code: int) -> ErrorCode:
    """将 HTTP 状态码映射为业务错误码（用于 envelope）。"""
    try:
        return ErrorCode(status_code)
    except ValueError:
        pass
    if status_code == 422:
        return ErrorCode.VALIDATION_ERROR
    if 400 <= status_code < 500:
        return ErrorCode.BAD_REQUEST
    return ErrorCode.INTERNAL_ERROR


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    """将 HTTPException 转为统一 envelope 响应（HTTP 200 + body.code）。"""
    code = _http_status_to_error_code(exc.status_code)
    return _envelope_response(code, message=exc.detail or message_for(code))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """将请求体验证错误转为 40001 + 校验详情。"""
    errors = exc.errors() if hasattr(exc, "errors") else []
    return _envelope_response(
        ErrorCode.VALIDATION_ERROR,
        message="请求参数校验失败",
        data={"details": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    """未捕获异常统一返回 500 envelope，避免泄露内部信息。"""
    _log.exception("unhandled exception")
    return _envelope_response(ErrorCode.INTERNAL_ERROR, message=message_for(ErrorCode.INTERNAL_ERROR))


@app.get("/health")
def health():
    """健康检查，供部署与探活使用。"""
    return {"status": "ok"}


app.include_router(auth_routes.router, prefix="/api/v1")
app.include_router(users_routes.router, prefix="/api/v1")
app.include_router(chat_routes.router, prefix="/api/v1")
app.include_router(compare_recommend_report_routes.router, prefix="/api/v1")
app.include_router(evidence_feedback_products_sessions_routes.router, prefix="/api/v1")
app.include_router(documents_routes.router, prefix="/api/v1")
app.include_router(knowledge_routes.router, prefix="/api/v1")
app.include_router(models_routes.router, prefix="/api/v1")
app.include_router(agents_routes.router, prefix="/api/v1")
app.include_router(rbac_routes.router, prefix="/api/v1")
app.include_router(skills_routes.router, prefix="/api/v1")
app.include_router(config_routes.router, prefix="/api/v1")
app.include_router(funds_routes.router, prefix="/api/v1")
app.include_router(fund_ratings_routes.router, prefix="/api/v1")

@app.get("/api/v1")
def api_root():
    """API 根，预留 /api/v1 前缀。"""
    return {"message": "ok", "version": "v1"}


def _run_dev():
    """开发时可直接 python -m api.main，端口由环境变量 PORT 指定（默认 8000）。"""
    import os
    import socket
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    # 手动创建 socket 并设置 SO_REUSEADDR，避免端口 TIME_WAIT 导致 bind 失败
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    config = uvicorn.Config(
        "api.main:app",
        host=host,
        port=port,
        reload=True,
    )
    server = uvicorn.Server(config)
    server.run(sockets=[sock])


if __name__ == "__main__":
    _run_dev()
