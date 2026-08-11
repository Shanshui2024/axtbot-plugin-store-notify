"""
QQ 消息构造与发送：markdown 消息 + 可选内嵌按钮（键盘）。
复用 AxTBot 框架的 MsgSender 与 QQ 消息模型。
"""
from __future__ import annotations

from app.classes import (
    Action,
    Button,
    Keyboard,
    KeyboardContent,
    Markdown,
    RenderData,
    Row,
    Sender,
)
from app.service.qq_service.MsgSender import send_group_message


def build_review_buttons(issue_number: int) -> list[Button]:
    """人工审核按钮：通过 / 拒绝"""
    return [
        Button(
            id=f"store_approve_{issue_number}",
            render_data=RenderData(label="✅ 通过", style=3),
            action=Action(type=1, data=f"approve:{issue_number}"),
        ),
        Button(
            id=f"store_reject_{issue_number}",
            render_data=RenderData(label="❌ 拒绝", style=2),
            action=Action(type=1, data=f"reject:{issue_number}"),
        ),
    ]


async def send_markdown(
    content: str,
    buttons: list[Button] | None = None,
) -> dict | None:
    """向配置的目标群发送 markdown 消息，可选携带按钮键盘。"""
    from .config import config

    if not config.group_openid:
        return None
    sender = Sender(msg_type=2, markdown=Markdown(content=content))
    if buttons:
        sender.keyboard = Keyboard(
            content=KeyboardContent(rows=[Row(buttons=buttons)])
        )
    return await send_group_message(config.group_openid, sender)


def md_issue_opened(payload: dict) -> str:
    """新插件申请 markdown"""
    issue = payload.get("issue", {})
    title = issue.get("title") or "(无标题)"
    user = issue.get("user", {}).get("login") or "未知"
    url = issue.get("html_url") or ""
    return (
        "### 🎉 新插件申请\n\n"
        f"**插件**：{title}\n\n"
        f"**申请人**：{user}\n\n"
        f"**状态**：自动验证中，通过后自动合入\n\n"
        f"[查看 Issue]({url})"
    )


def md_issue_closed(payload: dict) -> str:
    """插件申请结束 markdown"""
    issue = payload.get("issue", {})
    title = issue.get("title") or "(无标题)"
    labels = [lb.get("name", "") for lb in issue.get("labels", [])]
    state_reason = issue.get("state_reason") or ""
    url = issue.get("html_url") or ""

    if "plugin-approved" in labels:
        result = "✅ 已通过（自动或人工审批）"
    elif "plugin-rejected" in labels:
        result = "❌ 已拒绝"
    else:
        result = f"已关闭（{state_reason or 'completed'}）"
    return (
        "### 📋 插件申请结束\n\n"
        f"**插件**：{title}\n\n"
        f"**结果**：{result}\n\n"
        f"[查看 Issue]({url})"
    )


def md_review_required(plugin: dict, issue_url: str, issue_number: int) -> str:
    """需要人工审核 markdown（带按钮）"""
    name = plugin.get("name") or "未知"
    pypi = plugin.get("pypi") or ""
    author = plugin.get("author") or ""
    return (
        "### 🧐 插件需要人工审核\n\n"
        f"**插件**：{name}\n\n"
        f"**PyPI**：`{pypi}`\n\n"
        f"**作者**：{author}\n\n"
        "自动验证未通过，请在下方选择操作：\n\n"
        f"[Issue #{issue_number}]({issue_url})"
    )


def md_approved(plugin: dict, issue_url: str = "") -> str:
    """自动审批通过 markdown"""
    lines = [
        "### ✅ 插件已自动合入",
        "",
        f"**插件**：{plugin.get('name') or '未知'}",
        "",
        f"**PyPI**：`{plugin.get('pypi') or ''}`",
    ]
    if issue_url:
        lines += ["", f"[查看 Issue]({issue_url})"]
    return "\n".join(lines)


def md_version_result(updated: list, failed: list) -> str:
    """每日版本检查结果 markdown"""
    lines = ["### 📦 插件版本检查"]
    if updated:
        lines.append("\n**已更新**：")
        for item in updated:
            lines.append(f"- `{item.get('pypi')}` → `{item.get('version')}`")
    if failed:
        lines.append("\n**验证失败（需人工处理）**：")
        for item in failed:
            lines.append(
                f"- `{item.get('pypi')}`：`{item.get('current')}` → `{item.get('latest')}`"
            )
    if not updated and not failed:
        lines.append("\n本次无版本变更。")
    return "\n".join(lines)
