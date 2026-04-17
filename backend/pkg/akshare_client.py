"""
AkShare 数据获取客户端。

封装 AkShare API 调用，提供统一的数据访问接口。
特性：
- 重试机制：失败时重试 3 次，指数退避
- 限流机制：请求间隔 0.5-1 秒
- 缓存机制：使用内存缓存，TTL 5 分钟
- 异常处理：网络异常、数据格式异常
- 异步 API：使用 asyncio 提升性能
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import akshare as ak
import httpx

from pkg.logger import get_logger
from config.monitoring_config import get_akshare_metrics


class AkShareClient:
    """AkShare 数据获取客户端。
    
    提供统一的基金数据访问接口，支持重试、限流、缓存等特性。
    
    Attributes:
        max_retries: 最大重试次数
        retry_delay: 初始重试延迟（秒）
        request_interval: 请求间隔（秒）
        logger: 日志记录器
    
    Example:
        >>> client = AkShareClient()
        >>> result = await client.get_basic_info("000001")
        >>> if result["ok"]:
        ...     print(result["data"])
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        request_interval: float = 0.5,
        cache_ttl: int = 300,
        enable_cache: bool = True,
    ) -> None:
        """初始化 AkShare 客户端。
        
        Args:
            max_retries: 最大重试次数，默认 3 次
            retry_delay: 初始重试延迟（秒），默认 1.0 秒，使用指数退避
            request_interval: 请求间隔（秒），默认 0.5 秒，用于限流
            cache_ttl: 缓存过期时间（秒），默认 300 秒（5 分钟）
            enable_cache: 是否启用缓存，默认 True
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.request_interval = request_interval
        self.cache_ttl = cache_ttl
        self.enable_cache = enable_cache
        self.logger = get_logger(__name__)
        self._last_request_time: float = 0
        self._cache: Dict[str, Tuple[Any, float]] = {}
        # 经理大全缓存（避免反复全量拉取）
        self._fund_manager_records_cache: Optional[list[dict[str, Any]]] = None
        self._fund_manager_records_cache_time: float = 0.0
        
        # 缓存统计
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        
        self.logger.debug(
            "AkShareClient initialized",
            extra={
                "max_retries": max_retries,
                "retry_delay": retry_delay,
                "request_interval": request_interval,
                "cache_ttl": cache_ttl,
                "enable_cache": enable_cache,
            },
        )

    # ---------------------------------------------------------------------
    # 天天基金（东方财富）基金经理任职信息（用于任期/任职回报）
    # ---------------------------------------------------------------------

    async def get_manager_tenure(self, symbol: str) -> Dict[str, Any]:
        """获取基金经理管理本基金的任职信息（天数、起止日期、任职回报等）。

        数据源：天天基金 app 接口（fundmobapi.eastmoney.com）。
        目的：补齐“管理本基金年限”“任职期间年化回报”的计算所需字段。
        """
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            return {"ok": False, "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string."}

        cache_key = self._get_cache_key("get_manager_tenure", symbol=symbol)
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        url = "https://fundmobapi.eastmoney.com/FundMNewApi/FundMNMangerList"
        device_id = str(uuid.uuid4())
        params = {
            "FCODE": symbol,
            "plat": "Android",
            "appType": "ttjj",
            "product": "EFund",
            "Version": "6.2.4",
            "deviceid": device_id,
            "MobileKey": device_id,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": "https://fund.eastmoney.com/",
        }

        async def _fetch() -> Dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.post(url, params=params, headers=headers)
                raw = resp.content
                # 该接口偶发返回“看起来像 utf-8 但实际为 gbk”的内容，做双重解码兜底
                text: str
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("gbk", errors="replace")
                # 用 httpx 的 json 解析避免编码问题
                data = httpx.Response(status_code=resp.status_code, content=text.encode("utf-8")).json()
                if not isinstance(data, dict):
                    return {"ok": False, "message": "Invalid response format", "raw": text[:200]}
                if not data.get("Success") or data.get("ErrCode") not in (0, "0", None):
                    return {
                        "ok": False,
                        "message": str(data.get("ErrMsg") or data.get("ErrorMessage") or "Failed to fetch manager tenure"),
                        "data": [],
                    }
                items = data.get("Datas") or []
                if not isinstance(items, list):
                    items = []
                return {"ok": True, "data": items}
            except Exception as e:
                return {"ok": False, "message": str(e), "data": []}

        result = await _fetch()
        if result.get("ok"):
            self._set_to_cache(cache_key, result)
        return result

    async def get_manager_career(self, manager_names: list[str]) -> Dict[str, Any]:
        """获取基金经理从业经验（累计从业时间等）。

        当前实现基于 AkShare 的 fund_manager_em（东方财富基金经理大全）进行姓名匹配。
        """
        names = [n.strip() for n in (manager_names or []) if isinstance(n, str) and n.strip()]
        if not names:
            return {"ok": False, "message": "No manager names provided", "data": []}

        cache_key = self._get_cache_key("get_manager_career", names="|".join(sorted(set(names))))
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        # fund_manager_em 可能是全量表；做 24h 缓存
        now = time.time()
        if self._fund_manager_records_cache is None or (now - self._fund_manager_records_cache_time) > 86400:
            try:
                # 复用统一的重试/限流/异常处理逻辑
                fm = await self._retry_call(ak.fund_manager_em)
                if not fm.get("ok") or not isinstance(fm.get("data"), list):
                    return {"ok": False, "message": f"fund_manager_em fetch failed: {fm.get('message')}", "data": []}
                self._fund_manager_records_cache = [r for r in fm.get("data") or [] if isinstance(r, dict)]
                self._fund_manager_records_cache_time = now
            except Exception as e:
                return {"ok": False, "message": f"fund_manager_em fetch failed: {e}", "data": []}

        out: list[dict[str, Any]] = []
        records = self._fund_manager_records_cache or []

        def _pick_name(rec: dict[str, Any]) -> str:
            for k in ("姓名", "基金经理", "经理", "name"):
                v = rec.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            # 兜底：找包含“姓名/经理”的字段
            for k, v in rec.items():
                ks = str(k)
                if ("姓名" in ks or "经理" in ks) and v is not None and str(v).strip():
                    return str(v).strip()
            return ""

        def _pick_career(rec: dict[str, Any]) -> Any:
            for k in ("累计从业时间", "从业时间", "TOTALDAYS"):
                if k in rec:
                    return rec.get(k)
            for k, v in rec.items():
                ks = str(k)
                if "从业" in ks and v is not None and str(v).strip():
                    return v
            return None

        def _pick_org(rec: dict[str, Any]) -> Any:
            for k in ("所属公司", "基金公司", "公司", "JJGS"):
                if k in rec:
                    return rec.get(k)
            for k, v in rec.items():
                ks = str(k)
                if ("公司" in ks or "机构" in ks) and v is not None and str(v).strip():
                    return v
            return None

        # 建索引便于查找（姓名->若干记录）
        idx: dict[str, list[dict[str, Any]]] = {}
        for rec in records:
            nm = _pick_name(rec)
            if not nm:
                continue
            idx.setdefault(nm, []).append(rec)

        for n in names:
            for rec in idx.get(n, []):
                out.append(
                    {
                        "name": n,
                        "career": _pick_career(rec),
                        "org": _pick_org(rec),
                    }
                )

        result = {"ok": True, "data": out}
        self._set_to_cache(cache_key, result)
        return result

    async def get_rating_info(self, symbol: str) -> Dict[str, Any]:
        """获取基金评级信息（上海证券/招商证券/济安金信）。"""
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            return {"ok": False, "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string.", "data": {}}

        cache_key = self._get_cache_key("get_rating_info", symbol=symbol)
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

        def _find_code_key(rec: dict[str, Any]) -> str | None:
            for k in rec.keys():
                if "代码" in str(k):
                    return str(k)
            return None

        def _pick_star_fields(rec: dict[str, Any]) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for k, v in rec.items():
                ks = str(k)
                if "评级" in ks and ("3年" in ks or "5年" in ks):
                    out[ks] = v
            return out

        async def _fetch_one(func: Any, agency: str) -> dict[str, Any]:
            rs = await self._retry_call(func)
            if not rs.get("ok") or not isinstance(rs.get("data"), list):
                return {"agency": agency, "ok": False, "message": rs.get("message"), "record": None}
            rows = [r for r in rs.get("data") or [] if isinstance(r, dict)]
            hit = None
            for r in rows:
                code_key = _find_code_key(r)
                if code_key and str(r.get(code_key) or "").strip() == symbol:
                    hit = r
                    break
            if hit is None:
                return {"agency": agency, "ok": False, "message": f"symbol {symbol} not found", "record": None}
            return {
                "agency": agency,
                "ok": True,
                "record": {
                    "raw": hit,
                    "stars": _pick_star_fields(hit),
                },
            }

        sh, zs, ja = await asyncio.gather(
            _fetch_one(ak.fund_rating_sh, "上海证券"),
            _fetch_one(ak.fund_rating_zs, "招商证券"),
            _fetch_one(ak.fund_rating_ja, "济安金信"),
        )

        data = {"sh": sh, "zs": zs, "ja": ja}
        result = {"ok": any(x.get("ok") for x in [sh, zs, ja]), "data": data}
        self._set_to_cache(cache_key, result)
        return result
    
    async def _rate_limit(self) -> None:
        """限流控制：确保请求间隔满足配置要求。
        
        通过记录上次请求时间，计算距离当前的时间间隔，
        如果间隔小于配置的 request_interval，则等待剩余时间。
        这样可以避免请求过于频繁导致被 AkShare 限流或封禁。
        """
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_interval:
            wait_time = self.request_interval - elapsed
            self.logger.debug(
                f"Rate limiting: waiting {wait_time:.2f}s",
                extra={"elapsed": elapsed, "wait_time": wait_time},
            )
            await asyncio.sleep(wait_time)
        self._last_request_time = time.time()
    
    def _get_cache_key(self, method_name: str, **kwargs: Any) -> str:
        """生成缓存键。
        
        Args:
            method_name: 方法名称
            **kwargs: 方法参数
        
        Returns:
            缓存键，格式：{method_name}:{param1}:{param2}
        
        Example:
            >>> self._get_cache_key("get_basic_info", symbol="000001")
            'get_basic_info:000001'
            >>> self._get_cache_key("get_nav_data", symbol="000001", period="1年")
            'get_nav_data:000001:1年'
        """
        # 按键排序以确保相同参数生成相同的缓存键
        sorted_params = sorted(kwargs.items())
        param_str = ":".join(str(v) for k, v in sorted_params)
        return f"{method_name}:{param_str}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """从缓存获取数据。
        
        Args:
            cache_key: 缓存键
        
        Returns:
            缓存的数据，如果不存在或已过期则返回 None
        """
        # 提取缓存类型（从 cache_key 中提取方法名）
        cache_type = cache_key.split(":")[0].replace("get_", "")
        metrics = get_akshare_metrics()
        
        if cache_key in self._cache:
            data, expire_time = self._cache[cache_key]
            current_time = time.time()
            
            if current_time < expire_time:
                # 缓存未过期，命中
                self._cache_hits += 1
                metrics.record_cache_hit(cache_type)
                self.logger.debug(
                    f"Cache hit for {cache_key}",
                    extra={
                        "cache_key": cache_key,
                        "cache_hits": self._cache_hits,
                        "cache_misses": self._cache_misses,
                    },
                )
                return data
            else:
                # 缓存已过期，删除
                del self._cache[cache_key]
                self.logger.debug(
                    f"Cache expired for {cache_key}",
                    extra={"cache_key": cache_key},
                )
        
        # 缓存未命中
        self._cache_misses += 1
        metrics.record_cache_miss(cache_type)
        return None
    
    def _set_to_cache(self, cache_key: str, data: Any) -> None:
        """设置缓存。
        
        Args:
            cache_key: 缓存键
            data: 要缓存的数据
        """
        if not self.enable_cache:
            return
        
        expire_time = time.time() + self.cache_ttl
        self._cache[cache_key] = (data, expire_time)
        self.logger.debug(
            f"Cached data for {cache_key}",
            extra={"cache_key": cache_key, "expire_time": expire_time},
        )
    
    async def _retry_call(
        self,
        func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """带重试机制的 API 调用。
        
        使用指数退避策略进行重试：
        - 第 1 次失败：等待 retry_delay 秒（默认 1s）
        - 第 2 次失败：等待 retry_delay * 2 秒（默认 2s）
        - 第 3 次失败：等待 retry_delay * 4 秒（默认 4s）
        
        Args:
            func: 要调用的 AkShare 函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            成功时返回 {"ok": True, "data": [...]}
            失败时返回 {"ok": False, "message": "错误信息"}
        
        Example:
            >>> result = await self._retry_call(
            ...     ak.fund_individual_basic_info_xq,
            ...     symbol="000001"
            ... )
        """
        func_name = getattr(func, "__name__", str(func))
        
        for attempt in range(self.max_retries):
            try:
                # 限流控制
                await self._rate_limit()
                
                # 在线程池中执行同步的 AkShare 调用
                self.logger.debug(
                    f"Calling {func_name} (attempt {attempt + 1}/{self.max_retries})",
                    extra={
                        "func": func_name,
                        "func_args": str(args),
                        "func_kwargs": str(kwargs),
                        "attempt": attempt + 1,
                    },
                )
                
                result = await asyncio.to_thread(func, *args, **kwargs)
                
                # 成功：将 DataFrame 转换为字典列表
                if hasattr(result, "to_dict"):
                    data = result.to_dict(orient="records")
                else:
                    data = result
                
                self.logger.info(
                    f"{func_name} succeeded",
                    extra={
                        "func": func_name,
                        "attempt": attempt + 1,
                        "data_size": len(data) if isinstance(data, list) else 1,
                    },
                )
                
                return {"ok": True, "data": data}
                
            except Exception as e:
                error_msg = str(e)
                self.logger.warning(
                    f"{func_name} attempt {attempt + 1} failed: {error_msg}",
                    extra={
                        "func": func_name,
                        "func_args": str(args),
                        "func_kwargs": str(kwargs),
                        "attempt": attempt + 1,
                        "error": error_msg,
                    },
                )
                
                # 如果还有重试机会，则等待后重试
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    self.logger.debug(
                        f"Retrying after {delay}s",
                        extra={"delay": delay, "next_attempt": attempt + 2},
                    )
                    await asyncio.sleep(delay)
                else:
                    # 所有重试都失败
                    self.logger.error(
                        f"{func_name} all retries failed: {error_msg}",
                        extra={
                            "func": func_name,
                            "func_args": str(args),
                            "func_kwargs": str(kwargs),
                            "total_attempts": self.max_retries,
                            "error": error_msg,
                        },
                    )
                    return {"ok": False, "message": error_msg}
        
        # 理论上不会到达这里，但为了类型安全
        return {"ok": False, "message": "Unknown error"}

    async def get_basic_info(self, symbol: str) -> Dict[str, Any]:
        """获取基金基本信息。
        
        调用 AkShare 的 fund_individual_basic_info_xq 接口获取基金的基本信息，
        包括基金名称、类型、规模、基金经理、成立日期等核心信息。
        
        Args:
            symbol: 基金代码，6 位数字字符串，例如 "000001"
        
        Returns:
            成功时返回 {"ok": True, "data": [...]}
            失败时返回 {"ok": False, "message": "错误信息"}
        
        Example:
            >>> client = AkShareClient()
            >>> result = await client.get_basic_info("000001")
            >>> if result["ok"]:
            ...     print(result["data"])
        """
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            self.logger.error(
                "Invalid fund symbol format",
                extra={"symbol": symbol},
            )
            return {
                "ok": False,
                "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string.",
            }
        
        # 生成缓存键
        cache_key = self._get_cache_key("get_basic_info", symbol=symbol)
        
        # 尝试从缓存获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            self.logger.info(f"Cache hit for {cache_key}")
            return cached_data
        
        # 缓存未命中，调用 API
        self.logger.info(f"Cache miss for {cache_key}")
        result = await self._retry_call(
            ak.fund_individual_basic_info_xq,
            symbol=symbol,
        )
        
        # 如果成功，存入缓存
        if result.get("ok"):
            self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_achievement(self, symbol: str) -> Dict[str, Any]:
        """获取基金业绩表现数据。
        
        调用 AkShare 的 fund_individual_achievement_xq 接口获取基金的业绩表现数据，
        包括近 1 月、3 月、6 月、1 年、3 年等各时间段的收益率和同类排名。
        
        Args:
            symbol: 基金代码，6 位数字字符串，例如 "000001"
        
        Returns:
            成功时返回 {"ok": True, "data": [...]}
            失败时返回 {"ok": False, "message": "错误信息"}
        
        Example:
            >>> client = AkShareClient()
            >>> result = await client.get_achievement("000001")
            >>> if result["ok"]:
            ...     for record in result["data"]:
            ...         print(f"{record['时间段']}: {record['收益率']}")
        """
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            self.logger.error(
                "Invalid fund symbol format",
                extra={"symbol": symbol},
            )
            return {
                "ok": False,
                "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string.",
            }
        
        # 生成缓存键
        cache_key = self._get_cache_key("get_achievement", symbol=symbol)
        
        # 尝试从缓存获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            self.logger.info(f"Cache hit for {cache_key}")
            return cached_data
        
        # 缓存未命中，调用 API
        self.logger.info(f"Cache miss for {cache_key}")
        result = await self._retry_call(
            ak.fund_individual_achievement_xq,
            symbol=symbol,
        )
        
        # 如果成功，存入缓存
        if result.get("ok"):
            self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_analysis(self, symbol: str) -> Dict[str, Any]:
        """获取基金风险指标数据。
        
        调用 AkShare 的 fund_individual_analysis_xq 接口获取基金的风险指标数据，
        包括波动率、夏普比率、最大回撤等风险收益特征指标。
        
        Args:
            symbol: 基金代码，6 位数字字符串，例如 "000001"
        
        Returns:
            成功时返回 {"ok": True, "data": [...]}
            失败时返回 {"ok": False, "message": "错误信息"}
        
        Example:
            >>> client = AkShareClient()
            >>> result = await client.get_analysis("000001")
            >>> if result["ok"]:
            ...     for record in result["data"]:
            ...         print(f"波动率: {record.get('波动率')}")
        """
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            self.logger.error(
                "Invalid fund symbol format",
                extra={"symbol": symbol},
            )
            return {
                "ok": False,
                "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string.",
            }
        
        # 生成缓存键
        cache_key = self._get_cache_key("get_analysis", symbol=symbol)
        
        # 尝试从缓存获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            self.logger.info(f"Cache hit for {cache_key}")
            return cached_data
        
        # 缓存未命中，调用 API
        self.logger.info(f"Cache miss for {cache_key}")
        result = await self._retry_call(
            ak.fund_individual_analysis_xq,
            symbol=symbol,
        )
        
        # 如果成功，存入缓存
        if result.get("ok"):
            self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_detail_hold(self, symbol: str) -> Dict[str, Any]:
        """获取基金资产配置数据。
        
        调用 AkShare 的 fund_individual_detail_hold_xq 接口获取基金的资产配置数据，
        包括股票、债券、现金、其他资产的占比等信息。
        
        Args:
            symbol: 基金代码，6 位数字字符串，例如 "000001"
        
        Returns:
            成功时返回 {"ok": True, "data": [...]}
            失败时返回 {"ok": False, "message": "错误信息"}
        
        Example:
            >>> client = AkShareClient()
            >>> result = await client.get_detail_hold("000001")
            >>> if result["ok"]:
            ...     for record in result["data"]:
            ...         print(f"{record['资产类型']}: {record['仓位占比']}%")
        """
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            self.logger.error(
                "Invalid fund symbol format",
                extra={"symbol": symbol},
            )
            return {
                "ok": False,
                "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string.",
            }
        
        # 生成缓存键
        cache_key = self._get_cache_key("get_detail_hold", symbol=symbol)
        
        # 尝试从缓存获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            self.logger.info(f"Cache hit for {cache_key}")
            return cached_data
        
        # 缓存未命中，调用 API
        self.logger.info(f"Cache miss for {cache_key}")
        result = await self._retry_call(
            ak.fund_individual_detail_hold_xq,
            symbol=symbol,
        )
        
        # 如果成功，存入缓存
        if result.get("ok"):
            self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_detail_info(self, symbol: str) -> Dict[str, Any]:
        """获取基金费率信息数据。
        
        调用 AkShare 的 fund_individual_detail_info_xq 接口获取基金的费率信息，
        包括管理费、托管费、申购费、赎回费等各项费用信息。
        
        Args:
            symbol: 基金代码，6 位数字字符串，例如 "000001"
        
        Returns:
            成功时返回 {"ok": True, "data": [...]}
            失败时返回 {"ok": False, "message": "错误信息"}
        
        Example:
            >>> client = AkShareClient()
            >>> result = await client.get_detail_info("000001")
            >>> if result["ok"]:
            ...     for record in result["data"]:
            ...         print(f"管理费: {record.get('管理费率')}")
        """
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            self.logger.error(
                "Invalid fund symbol format",
                extra={"symbol": symbol},
            )
            return {
                "ok": False,
                "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string.",
            }
        
        # 生成缓存键
        cache_key = self._get_cache_key("get_detail_info", symbol=symbol)
        
        # 尝试从缓存获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            self.logger.info(f"Cache hit for {cache_key}")
            return cached_data
        
        # 缓存未命中，调用 API
        self.logger.info(f"Cache miss for {cache_key}")
        result = await self._retry_call(
            ak.fund_individual_detail_info_xq,
            symbol=symbol,
        )
        
        # 如果成功，存入缓存
        if result.get("ok"):
            self._set_to_cache(cache_key, result)
        
        return result
    
    async def get_nav_data(
        self,
        symbol: str,
        period: str = "1年",
    ) -> Dict[str, Any]:
        """获取基金净值走势数据。
        
        调用 AkShare 的 fund_open_fund_info_em 接口获取基金的净值走势数据，
        包括逐日的单位净值和日增长率，用于绘制净值走势图。
        
        Args:
            symbol: 基金代码，6 位数字字符串，例如 "000001"
            period: 时间周期，可选值：
                - "1月": 近 1 个月
                - "3月": 近 3 个月
                - "6月": 近 6 个月
                - "1年": 近 1 年（默认）
                - "3年": 近 3 年
                - "成立来": 自成立以来
        
        Returns:
            成功时返回 {"ok": True, "data": [...]}
            失败时返回 {"ok": False, "message": "错误信息"}
        
        Example:
            >>> client = AkShareClient()
            >>> result = await client.get_nav_data("000001", period="1年")
            >>> if result["ok"]:
            ...     for record in result["data"]:
            ...         print(f"{record['净值日期']}: {record['单位净值']}")
        """
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            self.logger.error(
                "Invalid fund symbol format",
                extra={"symbol": symbol},
            )
            return {
                "ok": False,
                "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string.",
            }
        
        # 验证 period 参数
        valid_periods = ["1月", "3月", "6月", "1年", "3年", "成立来"]
        if period not in valid_periods:
            self.logger.warning(
                f"Invalid period '{period}', using default '1年'",
                extra={"symbol": symbol, "period": period},
            )
            period = "1年"
        
        # 生成缓存键
        cache_key = self._get_cache_key("get_nav_data", symbol=symbol, period=period)
        
        # 尝试从缓存获取
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            self.logger.info(f"Cache hit for {cache_key}")
            return cached_data
        
        # 缓存未命中，调用 API
        self.logger.info(f"Cache miss for {cache_key}")
        result = await self._retry_call(
            ak.fund_open_fund_info_em,
            symbol=symbol,
            indicator="单位净值走势",
            period=period,
        )
        
        # 重要：部分数据源会忽略 period 参数，返回全历史数据。
        # 为保证“近1月/近3月/近1年/成立以来”切换可用，这里按日期再做一次裁剪。
        if result.get("ok") and isinstance(result.get("data"), list):
            try:
                result["data"] = self._filter_nav_records_by_period(result["data"], period)
            except Exception as e:
                # 裁剪失败不影响主流程，仅记录 debug
                self.logger.debug(
                    "nav_data period filter failed",
                    extra={"symbol": symbol, "period": period, "error": str(e)},
                )

        # 如果成功，存入缓存
        if result.get("ok"):
            self._set_to_cache(cache_key, result)
        
        return result

    @staticmethod
    def _filter_nav_records_by_period(records: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
        """
        将净值时序 records 按 period 裁剪为近似窗口。
        - 使用 records 中最大日期作为“截止日”
        - 近1月=30天，近3月=90天，近6月=180天，近1年=365天，近3年=1095天
        - 成立来：不裁剪
        """
        if not records or period == "成立来":
            return records

        days_map = {
            "1月": 30,
            "3月": 90,
            "6月": 180,
            "1年": 365,
            "3年": 365 * 3,
        }
        days = days_map.get(period)
        if not days:
            return records

        def _pick_date_str(rec: dict[str, Any]) -> str:
            d = rec.get("净值日期") or rec.get("日期") or rec.get("date")
            return str(d).strip() if d is not None else ""

        parsed: list[tuple[datetime, dict[str, Any]]] = []
        for r in records:
            if not isinstance(r, dict):
                continue
            ds = _pick_date_str(r)
            if not ds:
                continue
            try:
                dt = datetime.strptime(ds[:10], "%Y-%m-%d")
            except Exception:
                # 兼容极少数 YYYY/MM/DD
                try:
                    dt = datetime.strptime(ds[:10].replace("/", "-"), "%Y-%m-%d")
                except Exception:
                    continue
            parsed.append((dt, r))

        if not parsed:
            return records

        end_dt = max(dt for dt, _ in parsed)
        start_dt = end_dt - timedelta(days=days)
        filtered = [r for dt, r in parsed if dt >= start_dt]

        # 保留原始顺序（records 通常按时间升序；但为稳妥，按日期排序输出）
        filtered.sort(key=lambda rec: (_pick_date_str(rec) or ""))
        return filtered or records
    
    async def get_all_data(self, symbol: str) -> Dict[str, Any]:
        """并发获取单只基金的所有数据。
        
        使用 asyncio.gather 并发调用 6 个核心数据获取方法，
        通过 Semaphore 限制并发数为 3，避免请求过于频繁。
        使用 return_exceptions=True 确保部分失败不影响其他数据获取。
        
        Args:
            symbol: 基金代码，6 位数字字符串，例如 "000001"
        
        Returns:
            成功时返回包含所有数据的字典：
            {
                "ok": True,
                "data": {
                    "symbol": "000001",
                    "basic_info": {"ok": True, "data": [...]},
                    "achievement": {"ok": True, "data": [...]},
                    "analysis": {"ok": True, "data": [...]},
                    "detail_hold": {"ok": True, "data": [...]},
                    "detail_info": {"ok": True, "data": [...]},
                    "nav_data": {"ok": True, "data": [...]}
                }
            }
            
            如果所有方法都失败，返回：
            {
                "ok": False,
                "message": "Failed to fetch any data for symbol {symbol}"
            }
        
        Example:
            >>> client = AkShareClient()
            >>> result = await client.get_all_data("000001")
            >>> if result["ok"]:
            ...     basic_info = result["data"]["basic_info"]
            ...     if basic_info["ok"]:
            ...         print(basic_info["data"])
        """
        if not symbol or not symbol.isdigit() or len(symbol) != 6:
            self.logger.error(
                "Invalid fund symbol format",
                extra={"symbol": symbol},
            )
            return {
                "ok": False,
                "message": f"Invalid fund symbol: {symbol}. Expected 6-digit string.",
            }
        
        self.logger.info(
            f"Starting concurrent data fetch for {symbol}",
            extra={"symbol": symbol},
        )
        
        # 创建 Semaphore 限制并发数为 3
        semaphore = asyncio.Semaphore(3)
        
        async def fetch_with_semaphore(coro):
            """使用 Semaphore 控制并发的包装函数。"""
            async with semaphore:
                return await coro
        
        # 创建 6 个并发任务
        tasks = [
            fetch_with_semaphore(self.get_basic_info(symbol)),
            fetch_with_semaphore(self.get_achievement(symbol)),
            fetch_with_semaphore(self.get_analysis(symbol)),
            fetch_with_semaphore(self.get_detail_hold(symbol)),
            fetch_with_semaphore(self.get_detail_info(symbol)),
            fetch_with_semaphore(self.get_nav_data(symbol)),
        ]
        
        # 并发执行，return_exceptions=True 确保异常不会中断其他任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        basic_info, achievement, analysis, detail_hold, detail_info, nav_data = results
        
        # 将异常转换为错误响应
        def handle_result(result, name):
            if isinstance(result, Exception):
                self.logger.warning(
                    f"Exception in {name}: {result}",
                    extra={"symbol": symbol, "method": name, "error": str(result)},
                )
                return {"ok": False, "message": str(result)}
            return result
        
        basic_info = handle_result(basic_info, "get_basic_info")
        achievement = handle_result(achievement, "get_achievement")
        analysis = handle_result(analysis, "get_analysis")
        detail_hold = handle_result(detail_hold, "get_detail_hold")
        detail_info = handle_result(detail_info, "get_detail_info")
        nav_data = handle_result(nav_data, "get_nav_data")
        
        # 检查是否所有方法都失败
        all_failed = all(
            not result.get("ok", False)
            for result in [basic_info, achievement, analysis, detail_hold, detail_info, nav_data]
        )
        
        if all_failed:
            self.logger.error(
                f"All data fetch methods failed for {symbol}",
                extra={"symbol": symbol},
            )
            return {
                "ok": False,
                "message": f"Failed to fetch any data for symbol {symbol}",
            }
        
        # 记录成功和失败的方法数量
        success_count = sum(
            1 for result in [basic_info, achievement, analysis, detail_hold, detail_info, nav_data]
            if result.get("ok", False)
        )
        
        self.logger.info(
            f"Completed data fetch for {symbol}: {success_count}/6 methods succeeded",
            extra={
                "symbol": symbol,
                "success_count": success_count,
                "total_count": 6,
            },
        )
        
        # 额外：基金经理任期/任职回报（天天基金）与从业经验（AkShare 经理大全）
        manager_tenure: dict[str, Any] = {"ok": False, "data": [], "message": "not fetched"}
        manager_career: dict[str, Any] = {"ok": False, "data": [], "message": "not fetched"}
        # rating_info 默认不拉取（第三方评级页面体积大且网络抖动时极慢，可能拖慢整次对话）
        rating_info: dict[str, Any] = {"ok": False, "data": {}, "message": "not fetched (lazy)"}
        try:
            manager_tenure = await self.get_manager_tenure(symbol)
        except Exception as e:
            manager_tenure = {"ok": False, "message": str(e), "data": []}

        # 从 basic_info 中提取基金经理姓名列表用于从业经验匹配
        try:
            mgr_names: list[str] = []
            if basic_info.get("ok") and isinstance(basic_info.get("data"), list):
                for r in basic_info.get("data") or []:
                    if isinstance(r, dict) and str(r.get("item") or "").strip() == "基金经理":
                        val = str(r.get("value") or "").strip()
                        if val:
                            # 常见分隔符：'、' '/' ',' '，' ';' 以及空格/换行
                            import re

                            parts = re.split(r"[、/;,，\s]+", val)
                            mgr_names = [p.strip() for p in parts if p.strip()]
                        break
            if mgr_names:
                # 经理大全偶发较慢；不阻塞主流程，超时降级
                try:
                    manager_career = await asyncio.wait_for(self.get_manager_career(mgr_names), timeout=6.0)
                except asyncio.TimeoutError:
                    manager_career = {"ok": False, "message": "manager_career timeout", "data": []}
        except Exception as e:
            manager_career = {"ok": False, "message": str(e), "data": []}

        # rating_info：保持懒加载，不在 get_all_data 中拉取

        # 多周期净值（与上方 nav_data 默认 1 年互补；近1 年直接复用 nav_data，避免重复请求）
        nav_data_periods: dict[str, Any] = {"近1年": nav_data}
        nav_period_map = [
            ("近1月", "1月"),
            ("近3月", "3月"),
            ("成立以来", "成立来"),
        ]
        for label, period in nav_period_map:
            try:
                nav_data_periods[label] = await self.get_nav_data(symbol, period=period)
            except Exception as e:
                nav_data_periods[label] = {"ok": False, "message": str(e), "data": []}

        return {
            "ok": True,
            "data": {
                "symbol": symbol,
                "basic_info": basic_info,
                "achievement": achievement,
                "analysis": analysis,
                "detail_hold": detail_hold,
                "detail_info": detail_info,
                "nav_data": nav_data,
                "manager_tenure": manager_tenure,
                "manager_career": manager_career,
                "rating_info": rating_info,
                "nav_data_periods": nav_data_periods,
            },
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息。
        
        Returns:
            包含缓存统计信息的字典：
            {
                "cache_hits": 缓存命中次数,
                "cache_misses": 缓存未命中次数,
                "total_requests": 总请求次数,
                "hit_rate": 缓存命中率（百分比）,
                "cache_size": 当前缓存条目数
            }
        
        Example:
            >>> client = AkShareClient()
            >>> # ... 执行一些请求 ...
            >>> stats = client.get_cache_stats()
            >>> print(f"缓存命中率: {stats['hit_rate']:.2f}%")
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0.0
        
        stats = {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "cache_size": len(self._cache),
        }
        
        self.logger.info(
            f"Cache statistics: {self._cache_hits} hits, {self._cache_misses} misses, "
            f"{hit_rate:.2f}% hit rate, {len(self._cache)} cached items",
            extra=stats,
        )
        
        return stats
    
    def clear_cache(self) -> None:
        """清空缓存。
        
        清空所有缓存数据，但保留缓存统计信息。
        
        Example:
            >>> client = AkShareClient()
            >>> client.clear_cache()
        """
        cache_size = len(self._cache)
        self._cache.clear()
        self.logger.info(
            f"Cache cleared: {cache_size} items removed",
            extra={"cache_size_before": cache_size},
        )
    
    def reset_cache_stats(self) -> None:
        """重置缓存统计信息。
        
        将缓存命中和未命中计数器重置为 0。
        
        Example:
            >>> client = AkShareClient()
            >>> client.reset_cache_stats()
        """
        self._cache_hits = 0
        self._cache_misses = 0
        self.logger.info("Cache statistics reset")
