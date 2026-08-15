from __future__ import annotations

from app import on_interaction
from app.classes import PluginMetadata, QQInteraction
from app.main import app as _app
from app.modules import logger
from app.service.qq_service.Interact import interaction_reply

from . import github_api, notify
from .config import config
from .server import router as _store_router

__meta__ = PluginMetadata(
    name="插件商店通知",
    version="1.0.2",
    author="Shanshui2024",
    description="接收插件商店 Webhook，推送审核消息到指定 QQ 群，支持按钮审批",
    official=False,
)

# 把本插件的 Webhook 路由挂到 AxTBot 自己的 FastAPI 实例上：
# 复用 AxTBot 主 ip:port，回调地址 /notify/* 与 QQ 回调 /webhook 区分开。
_app.include_router(_store_router)
logger.info("商店通知 >>> 已挂载 /notify/* 路由到 AxTBot FastAPI 实例")


def _extract_issue_number(button_id: str, button_data: str, action: str) -> int:
    """从按钮 id / data 中解析 issue 编号"""
    marker = f"{action}:"
    raw = ""
    if marker in button_data:
        raw = button_data.split(marker, 1)[1].strip()
    else:
        prefix = f"store_{action}_"
        if button_id.startswith(prefix):
            raw = button_id.split(prefix, 1)[1].strip()
    try:
        return int(raw)
    except ValueError:
        return 0


@on_interaction(interaction_type=11)
async def on_button(event: QQInteraction):
    """按钮互动：通过 / 拒绝 → GitHub issue 评论审批指令"""
    try:
        button_id = event.data.resolved.button_id or ""
        button_data = event.data.resolved.button_data or ""
        action = None
        if button_id.startswith("store_approve_") or button_data.startswith("approve:"):
            action = "approve"
        elif button_id.startswith("store_reject_") or button_data.startswith("reject:"):
            action = "reject"
        if action is None:
            return

        issue_number = _extract_issue_number(button_id, button_data, action)
        if issue_number <= 0:
            logger.warning(
                f"商店通知 >>> 按钮缺少有效 issue 号: id={button_id} data={button_data}"
            )
            await interaction_reply(event.id)
            return

        # 权限校验：配置了管理员 openid 时校验点击者
        clicker = event.group_member_openid or event.user_openid or ""
        if config.admin_openids:
            admins = [o.strip() for o in config.admin_openids.split(",") if o.strip()]
            if admins and clicker not in admins:
                logger.warning(
                    f"商店通知 >>> 非管理员 {clicker} 点击审批按钮，已忽略"
                )
                await interaction_reply(event.id)
                return

        if not config.github_token:
            logger.warning("商店通知 >>> 未配置 PLUGIN_STORE_GITHUB_TOKEN，无法审批")
            await interaction_reply(event.id)
            return

        body = "/approve" if action == "approve" else "/reject"
        status, data = await github_api.post_issue_comment(
            config.repo, issue_number, body, config.github_token
        )
        if 200 <= status < 300:
            logger.info(f"商店通知 >>> 已对 issue #{issue_number} 评论 {body}")
            url = f"https://github.com/{config.repo}/issues/{issue_number}"
            await notify.send_markdown(
                f"### ✅ 审批操作已提交\n\n已对 [Issue #{issue_number}]({url}) 评论 **{body}**。"
            )
        else:
            logger.error(f"商店通知 >>> 审批评论失败 HTTP {status}: {data}")
        await interaction_reply(event.id)
    except Exception as e:
        logger.error(f"商店通知 >>> 按钮处理异常: {e}")
        try:
            await interaction_reply(event.id)
        except Exception:
            pass
