"""
API 中间件：请求 ID 与 traceId 绑定、响应头回传；鉴权（Bearer Token → userId/role/productPoolIds）。

T028：鉴权依赖 T027a Token 校验；统一响应 envelope、X-Request-Id 见 main.py 与 pkg.codes。
"""
import uuid

from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.routing import Match

from pkg.logger import bind_trace_id, clear_trace_id
from pkg.codes import ErrorCode, envelope, message_for

from auth.service import verify_token
from rbac.store import get_user_role_codes, ensure_seed_admin

HEADER_REQUEST_ID = "X-Request-Id"

# 无需鉴权的路径（精确匹配或前缀）
_PUBLIC_PATHS = ("/health", "/api/v1", "/api/v1/auth/login")


def _is_public_path(path: str) -> bool:
    path = (path or "").split("?")[0].rstrip("/") or "/"
    return path in _PUBLIC_PATHS


def _get_bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization") or ""
    if not auth.strip().lower().startswith("bearer "):
        return ""
    return auth[7:].strip()

def _route_exists(request: Request) -> bool:
    """
    判断当前请求是否能匹配到任一路由（用于避免“未登录访问不存在路径”被误判为 401）。
    """
    app = getattr(request, "app", None)
    router = getattr(app, "router", None)
    routes = getattr(router, "routes", None) if router else None
    if not routes:
        return True
    scope = request.scope
    for r in routes:
        try:
            match, _child_scope = r.matches(scope)  # type: ignore[attr-defined]
        except Exception:
            continue
        if match == Match.FULL:
            return True
    return False


async def add_trace_id_middleware(request: Request, call_next) -> Response:
    """
    从请求头读取 X-Request-Id 作为 traceId，未传则生成 UUID；
    绑定到当前请求上下文，并在响应头回传同一值。
    """
    trace_id = request.headers.get(HEADER_REQUEST_ID) or str(uuid.uuid4())
    bind_trace_id(trace_id)
    try:
        response = await call_next(request)
        response.headers[HEADER_REQUEST_ID] = trace_id
        return response
    finally:
        clear_trace_id()


async def add_auth_middleware(request: Request, call_next) -> Response:
    """
    鉴权中间件：对 /api/v1 下除 /api/v1/auth/login、/api/v1 外的请求校验 Bearer Token，
    解析后注入 request.state.user_id、request.state.role、request.state.product_pool_ids。
    未携带或无效时返回 200 + envelope code=401。
    """
    path = request.scope.get("path", "") or ""
    if not _route_exists(request):
        return await call_next(request)
    if _is_public_path(path):
        return await call_next(request)
    token = _get_bearer_token(request)
    if not token:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.UNAUTHORIZED, message=message_for(ErrorCode.UNAUTHORIZED), data=None),
        )
    payload = verify_token(token)
    if not payload:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.UNAUTHORIZED, message="Token 无效或已过期", data=None),
        )
    user_id = payload.get("sub") or ""
    if not user_id:
        return JSONResponse(
            status_code=200,
            content=envelope(code=ErrorCode.UNAUTHORIZED, message="Token 无效", data=None),
        )
    request.state.user_id = user_id
    # 角色：优先从 RBAC 表读取（admin 账号自动绑定 admin）
    try:
        ensure_seed_admin()
        roles = get_user_role_codes(str(user_id))
        request.state.role = roles[0] if roles else None
    except Exception:
        request.state.role = payload.get("role")  # 兼容旧 token
    request.state.product_pool_ids = payload.get("product_pool_ids") if isinstance(payload.get("product_pool_ids"), list) else []
    return await call_next(request)
