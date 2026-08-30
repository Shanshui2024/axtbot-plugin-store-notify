"""GitHub REST API 调用：用于按钮审批（在 issue 上评论 /approve 或 /reject）。"""
from __future__ import annotations

import aiohttp

from . import github_app


async def post_issue_comment(
    repo: str,
    issue_number: int,
    body: str,
) -> tuple[int, dict]:
    """在指定 issue 上发布评论。

    令牌优先使用 GitHub App 的 installation token（评论归属于 App 身份），
    未配置 GitHub App 时回退到个人 PAT。
    """
    token = await github_app.get_access_token()
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json={"body": body}, headers=headers, timeout=15
        ) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}
            return resp.status, data
