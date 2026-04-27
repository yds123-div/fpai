"""
诊断脚本：验证基金数据源是否被拒绝抓取/被风控。

运行：
  python scripts/diag_test_data_sources.py

输出：
  - 每个 URL 的状态码、最终 URL（跟随跳转后）、Content-Type
  - 响应体前 200 字符（用于判断是否 HTML/错误页）
  - 若为 403，尝试从响应体里提取 “Your IP Address: x.x.x.x”
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass
class Check:
    name: str
    url: str
    method: str = "GET"
    allow_redirects: bool = True


def _snip(text: str, n: int = 200) -> str:
    s = (text or "").replace("\r", "").replace("\n", " ")
    return s[:n] + ("..." if len(s) > n else "")


def _looks_like_html(text: str) -> bool:
    t = (text or "").lstrip().lower()
    return t.startswith("<!doctype html") or t.startswith("<html") or "<head" in t[:400]


def _extract_ip_hint(text: str) -> str | None:
    m = re.search(r"Your IP Address:\s*([0-9.]+)", text or "")
    return m.group(1) if m else None


def run(checks: Iterable[Check]) -> int:
    try:
        import requests  # type: ignore
    except Exception as e:
        print(f"[FATAL] missing requests: {e}")
        return 2

    headers = {
        # 伪装常见浏览器 UA，减少直接风控
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }

    for c in checks:
        print("=" * 88)
        print(f"[CHECK] {c.name}")
        print(f"  method={c.method} allow_redirects={c.allow_redirects}")
        print(f"  url={c.url}")
        try:
            resp = requests.request(
                c.method,
                c.url,
                headers=headers,
                timeout=20,
                allow_redirects=c.allow_redirects,
            )
            ct = resp.headers.get("content-type", "")
            text = ""
            try:
                resp.encoding = resp.apparent_encoding  # best-effort
                text = resp.text or ""
            except Exception:
                text = ""

            print(f"  status={resp.status_code}")
            print(f"  final_url={getattr(resp, 'url', '')}")
            print(f"  content_type={ct}")
            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                print(f"  redirect_location={resp.headers.get('location')}")

            if resp.status_code == 403:
                ip = _extract_ip_hint(text)
                if ip:
                    print(f"  [HINT] 403 with IP hint: {ip}")
            if _looks_like_html(text):
                print("  [HINT] response looks like HTML (可能是风控页/notfound/验证码页)")

            print(f"  body_snip={_snip(text)}")
        except Exception as e:
            print(f"  [ERROR] request failed: {e}")

    print("=" * 88)
    return 0


if __name__ == "__main__":
    checks = [
        Check(
            name="Danjuan fund detail (蛋卷)",
            url="https://danjuanfunds.com/djapi/fund/detail/000012",
            allow_redirects=True,
        ),
        Check(
            name="Danjuan asset percent (蛋卷持仓/资产占比)",
            url="https://danjuanfunds.com/djapi/fundx/base/fund/record/asset/percent?fund_code=000012&report_date=2023-12-31",
            allow_redirects=True,
        ),
        Check(
            name="Eastmoney pingzhongdata (东财净值JS，不跟随跳转)",
            url="https://fund.eastmoney.com/pingzhongdata/000012.js",
            allow_redirects=False,
        ),
        Check(
            name="Eastmoney pingzhongdata (东财净值JS，跟随跳转)",
            url="https://fund.eastmoney.com/pingzhongdata/000012.js",
            allow_redirects=True,
        ),
        Check(
            name="Eastmoney FundMob manager list (天天基金APP接口)",
            url="https://fundmobapi.eastmoney.com/FundMNewApi/FundMNMangerList?FCODE=000012&plat=Android&appType=ttjj&product=EFund&Version=6.2.4&deviceid=diag&MobileKey=diag",
            method="POST",
            allow_redirects=True,
        ),
    ]
    sys.exit(run(checks))

