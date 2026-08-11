"""
Webhook 路由：直接挂载到 AxTBot 的 FastAPI 实例（复用 AxTBot 主 ip:port）。

端点（使用 /store-notify 前缀，与 QQ 回调 /webhook 区分）：
  POST /store-notify/github-webhook  接收 GitHub 官方 Webhook（X-GitHub-Event: issues）
  POST /store-notify/actions-webhook 接收 GitHub Actions 推送（Bearer 鉴权）
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.modules import logger

from . import notify
from .config import config

router = APIRouter(prefix="/store-notify", tags=["StoreNotify"])


# ============================================================
#  事件处理
# ============================================================

async def _handle_github_event(event_type: str, payload: dict) -> None:
    """GitHub 官方 Webhook：issues 事件 → 新申请 / 申请结束 通知"""
    try:
        if event_type != "issues":
            return
        action = payload.get("action")
        issue = payload.get("issue") or {}
        labels = [lb.get("name", "") for lb in issue.get("labels", [])]

        if action == "opened" and "plugin-request" in labels:
            await notify.send_markdown(notify.md_issue_opened(payload))
            logger.info("store-notify >>> 已推送新插件申请通知")
        elif action == "closed":
            await notify.send_markdown(notify.md_issue_closed(payload))
            logger.info("store-notify >>> 已推送插件申请结束通知")
    except Exception as e:
        logger.error(f"store-notify >>> 处理 GitHub Webhook 失败: {e}")


async def _handle_actions_event(payload: dict) -> None:
    """GitHub Actions 推送：审核状态事件 → markdown（可选带按钮）"""
    try:
        event = payload.get("event", "")
        plugin = payload.get("plugin") or {}
        issue_url = payload.get("issue") or ""
        issue_number = 0
        try:
            issue_number = int(issue_url.rstrip("/").split("/")[-1])
        except Exception:
            pass

        if event == "plugin_review_required":
            buttons = notify.build_review_buttons(issue_number) if issue_number else None
            await notify.send_markdown(
                notify.md_review_required(plugin, issue_url, issue_number), buttons
            )
            logger.info("store-notify >>> 已推送人工审核通知（含按钮）")
        elif event == "plugin_approved":
            await notify.send_markdown(notify.md_approved(plugin, issue_url))
            logger.info("store-notify >>> 已推送自动审批通过通知")
        elif event == "plugin_version_check":
            await notify.send_markdown(
                notify.md_version_result(
                    payload.get("updated") or [], payload.get("failed") or []
                )
            )
            logger.info("store-notify >>> 已推送版本检查结果")
    except Exception as e:
        logger.error(f"store-notify >>> 处理 Actions Webhook 失败: {e}")


def _dispatch(coro) -> None:
    """在运行中的事件循环中调度后台任务，并记录未捕获异常。"""
    task = asyncio.create_task(coro)

    def _done(t: asyncio.Task) -> None:
        try:
            t.result()
        except Exception as e:
            logger.error(f"store-notify >>> webhook 后台任务异常: {e}")

    task.add_done_callback(_done)


# ============================================================
#  鉴权
# ============================================================

def _verify_github_signature(body: bytes, sig_header: str | None) -> bool:
    if not config.github_secret or not sig_header:
        return False
    expected = "sha256=" + hmac.new(
        config.github_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


def _verify_actions_token(auth_header: str | None) -> bool:
    if not config.actions_token:
        return False
    return auth_header == f"Bearer {config.actions_token}"


# ============================================================
#  FastAPI 端点
# ============================================================

@router.post("/github-webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    body = await request.body()
    if not _verify_github_signature(body, x_hub_signature_256):
        return JSONResponse(
            status_code=401, content={"ok": False, "msg": "invalid signature"}
        )
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    _dispatch(_handle_github_event(x_github_event or "", payload))
    return {"ok": True, "msg": "accepted"}


@router.post("/actions-webhook")
async def actions_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
):
    if not _verify_actions_token(authorization):
        return JSONResponse(
            status_code=401, content={"ok": False, "msg": "invalid token"}
        )
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    _dispatch(_handle_actions_event(payload))
    return {"ok": True, "msg": "accepted"}
