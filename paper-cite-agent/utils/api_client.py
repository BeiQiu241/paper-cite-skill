"""HTTP 客户端工具，提供带重试的请求封装。"""

import time
import requests
from typing import Optional, Dict, Any


def get_with_retry(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
    backoff: float = 1.0,
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    """带指数退避重试的 GET 请求。返回 JSON 或 None。"""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait = backoff * (2 ** attempt)
                print(f"  [API] 请求被限速，等待 {wait:.1f}s 后重试...")
                time.sleep(wait)
                continue
            print(f"  [API] 请求失败 HTTP {resp.status_code}: {url}")
            return None
        except requests.exceptions.Timeout:
            print(f"  [API] 请求超时 (尝试 {attempt + 1}/{max_retries}): {url}")
        except requests.exceptions.ConnectionError as e:
            print(f"  [API] 连接错误: {e}")
            return None
        except Exception as e:
            print(f"  [API] 未知错误: {e}")
            return None
        time.sleep(backoff * (2 ** attempt))
    return None
