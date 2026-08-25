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
    Permission,
    RenderData,
    Row,
    Sender,
)
from app.service.qq_service.MsgSender import send_group_message

# QQ markdown 消息总长度限制较严，日志摘要需截断
MAX_LOG_CHARS = 800


def build_review_buttons(issue_number: int) -> list[Button]:
    """人工审核按钮：通过 / 拒绝。

    permission 必须显式设为所有人可点（type=2），
    否则平台按默认权限处理，普通成员点击会提示"无权限操作"。
    服务端仍由 config.admin_openids 做二次校验。
    """
    return [
        Button(
            id=f"store_approve_{issue_number}",
            render_data=RenderData(label="✅ 通过", style=3),
            action=Action(
                type=1,
                permission=Permission(type=2),
                data=f"approve:{issue_number}",
            ),
        ),
        Button(
            id=f"store_reject_{issue_number}",
            render_data=RenderData(label="❌ 拒绝", style=2),
            action=Action(
                type=1,
                permission=Permission(type=2),
                data=f"reject:{issue_number}",
            ),
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


def _clip(text: str, limit: int = MAX_LOG_CHARS) -> str:
    """保留末尾 limit 个字符（错误通常在日志尾部），并做整体长度兜底。"""
    text = (text or "").strip()
    if len(text) > limit:
        text = "...\n" + text[-limit:]
    return text


def md_review_required(
    plugin: dict,
    issue_url: str,
    issue_number: int,
    run_url: str = "",
    error_log: str = "",
) -> str:
    """需要人工审核 markdown（带按钮 + 可选运行错误日志）"""
    name = plugin.get("name") or "未知"
    pypi = plugin.get("pypi") or ""
    author = plugin.get("author") or ""
    lines = [
        "### 🧐 插件需要人工审核",
        "",
        f"**插件**：{name}",
        "",
        f"**PyPI**：`{pypi}`",
        "",
        f"**作者**：{author}",
        "",
        "自动验证未通过，请在下方选择操作：",
        "",
        f"[Issue #{issue_number}]({issue_url})",
    ]
    if run_url:
        lines += ["", f"[完整运行日志]({run_url})"]
    excerpt = _clip(error_log)
    if excerpt:
        lines += [
            "",
            "**❌ 运行错误日志（末尾摘要）**",
            "",
            "```text",
            excerpt,
            "```",
        ]
    return "\n".join(lines)


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


def md_version_result(updated: list, failed: list, run_url: str = "") -> str:
    """每日版本检查结果 markdown（failed 项可含 reason / error 字段）"""
    lines = ["### 📦 插件版本检查"]
    if run_url:
        lines += ["", f"[完整运行日志]({run_url})"]
    if updated:
        lines.append("")
        lines.append("**已更新**：")
        for item in updated:
            lines.append(f"- `{item.get('pypi')}` → `{item.get('version')}`")
    if failed:
        lines.append("")
        lines.append("**验证失败（需人工处理）**：")
        for item in failed:
            reason = item.get("reason") or ""
            suffix = f"（{reason}）" if reason else ""
            lines.append(
                f"- `{item.get('pypi')}`：`{item.get('current')}` → "
                f"`{item.get('latest')}`{suffix}"
            )
        # 错误日志摘要逐项附在列表后，避免破坏列表结构
        budget = MAX_LOG_CHARS
        for item in failed:
            error = (item.get("error") or "").strip()
            if not error:
                continue
            excerpt = _clip(error, budget)
            lines += [
                "",
                f"**`{item.get('pypi')}` 错误摘要**",
                "",
                "```text",
                excerpt,
                "```",
            ]
            budget = max(budget // 2, 200)
    if not updated and not failed:
        lines.append("")
        lines.append("本次无版本变更。")
    return "\n".join(lines)
