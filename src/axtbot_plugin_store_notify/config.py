"""
插件配置：从框架统一配置（local.env / 环境变量）中读取。
所有键以 PLUGIN_STORE_ 为前缀，避免与框架/其他插件冲突。
"""
from __future__ import annotations

from app.modules import config_loader


def _get(key: str, default: str = "") -> str:
    value = config_loader.get_raw_data().get(key, default)
    return str(value).strip() if value is not None else default


class Config:
    """插件运行配置"""

    # 说明：Webhook 路由直接挂载到 AxTBot 的 FastAPI 实例，
    # 复用 AxTBot 主 ip:port，无需再单独配置监听地址/端口。

    # GitHub 官方 Webhook 签名密钥（仓库 Settings → Webhooks → Secret）
    github_secret: str = _get("PLUGIN_STORE_GITHUB_SECRET")

    # GitHub Actions 推送鉴权 token（与 store 工作流的 AUTO_REVIEW_WEBHOOK_TOKEN 保持一致）
    actions_token: str = _get("PLUGIN_STORE_ACTIONS_TOKEN")

    # 通知目标 QQ 群 openid
    group_openid: str = _get("PLUGIN_STORE_GROUP_OPENID")

    # --- GitHub App 鉴权（评论归属于 App 身份，而非个人账号）---
    # 三者都配置时，审批评论通过 GitHub App 的 installation token 发送；
    # 留空则回退到下面的个人 PAT。私钥可填 PEM 全文，或指定私钥文件路径。
    github_app_id: str = _get("PLUGIN_STORE_GITHUB_APP_ID")
    github_app_private_key: str = _get("PLUGIN_STORE_GITHUB_APP_PRIVATE_KEY")
    github_app_private_key_path: str = _get("PLUGIN_STORE_GITHUB_APP_PRIVATE_KEY_PATH")
    github_app_installation_id: str = _get("PLUGIN_STORE_GITHUB_APP_INSTALLATION_ID")

    # 按钮审批所用的 GitHub Token（fallback，需 issues:write 权限的 fine-grained PAT）
    github_token: str = _get("PLUGIN_STORE_GITHUB_TOKEN")

    # 监听商店仓库
    repo: str = _get("PLUGIN_STORE_REPO", "AxT-Team/AxTBot-PluginStore")

    # 允许操作审批按钮的管理员 openid 列表（逗号分隔）；为空则不做成员校验
    admin_openids: str = _get("PLUGIN_STORE_ADMIN_OPENIDS")


config = Config()
