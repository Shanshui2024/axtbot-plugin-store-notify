"""GitHub App 鉴权：用 App ID + 私钥换取 installation access token。

相比个人 PAT，使用 GitHub App 的 installation token 时，issue 上的
/approve、/reject 评论会归属于 GitHub App（机器人身份），而不是某个个人账户。
"""
from __future__ import annotations

import base64
import json
import time

import aiohttp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from app.modules import logger

from .config import config


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _normalize_pem(raw: str) -> str:
    """支持环境里直接粘贴的 PEM（可能用 \\n 转义换行）。"""
    return raw.replace("\\n", "\n").strip()


def _load_private_key(pem: str):
    return load_pem_private_key(
        _normalize_pem(pem).encode("utf-8"), password=None
    )


def _build_jwt(app_id: str, private_key_pem: str) -> str:
    private_key = _load_private_key(private_key_pem)
    header = {"alg": "RS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 540,
        "iss": str(app_id),
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    ).encode("ascii")
    signature = private_key.sign(
        signing_input, padding.PKCS1v15(), hashes.SHA256()
    )
    return signing_input.decode("ascii") + "." + _b64url(signature)


class _InstallationTokenCache:
    """缓存 installation token，避免每次评论都重新走一遍 JWT 换取流程。"""

    def __init__(self) -> None:
        self.token: str | None = None
        self.expires_at: float = 0.0

    async def get(self) -> str:
        now = time.time()
        # installation token 有效期约 1 小时，提前 60s 刷新
        if self.token and now < self.expires_at - 60:
            return self.token
        self.token = await self._fetch()
        self.expires_at = now + 3300
        return self.token

    async def _fetch(self) -> str:
        jwt_token = _build_jwt(
            config.github_app_id, config.github_app_private_key
        )
        url = (
            "https://api.github.com/app/installations/"
            f"{config.github_app_installation_id}/access_tokens"
        )
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, timeout=15) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = {}
                if resp.status >= 400 or not data.get("token"):
                    raise RuntimeError(
                        f"获取 GitHub App installation token 失败 "
                        f"HTTP {resp.status}: {data}"
                    )
                return data["token"]


_cache = _InstallationTokenCache()


def is_app_configured() -> bool:
    return bool(
        config.github_app_id
        and (config.github_app_private_key or config.github_app_private_key_path)
        and config.github_app_installation_id
    )


async def get_access_token() -> str:
    """返回用于 GitHub API 的令牌。

    优先使用 GitHub App（installation token，评论归属于 App 身份）；
    未配置 GitHub App 时回退到个人 PAT；两者都没有则抛错。
    """
    if is_app_configured():
        try:
            pem = config.github_app_private_key
            if not pem and config.github_app_private_key_path:
                with open(config.github_app_private_key_path, "r", encoding="utf-8") as f:
                    pem = f.read()
            config.github_app_private_key = pem
            return await _cache.get()
        except Exception as e:
            logger.error(
                f"商店通知 >>> 通过 GitHub App 获取令牌失败，回退到 PAT: {e}"
            )
    if config.github_token:
        return config.github_token
    raise RuntimeError(
        "未配置 GitHub App 也未配置 PLUGIN_STORE_GITHUB_TOKEN，无法发起审批"
    )
