# axtbot-plugin-store-notify

AxTBot 插件商店通知：接收插件商店的 GitHub Webhook，把审核进度推送到指定 QQ 群。

- 新插件申请（GitHub issue `opened`）→ 群内 markdown 通知
- 插件申请结束（issue `closed`）→ 群内 markdown 通知
- 需要人工审核（自动验证失败）→ 群内 markdown + **通过 / 拒绝** 按钮
- 自动审批通过 / 每日版本检查 → 群内 markdown 通知
- 按钮点击 → 自动在 GitHub issue 评论 `/approve` 或 `/reject`，复用商店仓库的审批工作流

## 工作原理

```
GitHub 仓库 Webhook ──POST──▶ AxTBot FastAPI (/notify/github-webhook)   → 新申请 / 申请结束
GitHub Actions 推送 ──POST──▶ AxTBot FastAPI (/notify/actions-webhook) → 人工审核(按钮) / 自动合入 / 版本检查
                                         │
                                          ▼ 发送 markdown (+按钮)
                                   指定 QQ 群
                                         │ (点击按钮 → INTERACTION_CREATE)
                                         ▼
                              AxTBot 框架 /webhook 回调 → on_interaction
                                         │
                                         ▼
                     GitHub API 评论 /approve 或 /reject → 触发 plugin-approve.yml
```

本插件的 Webhook 路由**直接挂载到 AxTBot 的 FastAPI 实例**上：

- 复用 AxTBot 主服务的 ip:port，**不额外占用端口**；
- 路径使用 `/notify/*` 前缀，与 QQ 回调 `/webhook` 区分，互不冲突；
- 生命周期由 uvicorn 统一管理，无需手动起停。

## 安装

### 方式一：PyPI 包（推荐，框架通过 entry point 自动加载）

```bash
pip install axtbot-plugin-store-notify
```

安装后无需手动注册，AxTBot 启动时会通过 `axtbot.plugins` entry point 自动发现。

### 方式二：本地包

将 `src/axtbot_plugin_store_notify` 目录复制到 AxTBot 的 `plugins/` 目录下
（本地包方式，AxTBot 启动时自动加载，适合直接调试）。

> 注意：代码改动后需**重启 AxTBot** 才会生效。

## 配置

在 AxTBot 的 `local.env`（或环境变量）中配置，所有键以 `PLUGIN_STORE_` 为前缀：

| 配置项 | 必填 | 说明 |
|---|---|---|
| `PLUGIN_STORE_GITHUB_SECRET` | 是 | GitHub 官方 Webhook 签名密钥，与仓库 Webhook 的 Secret 一致 |
| `PLUGIN_STORE_ACTIONS_TOKEN` | 否* | GitHub Actions 推送鉴权 token，与仓库 Actions Secret `AUTO_REVIEW_WEBHOOK_TOKEN` 一致 |
| `PLUGIN_STORE_GROUP_OPENID` | 是 | 通知目标 QQ 群 openid |
| `PLUGIN_STORE_GITHUB_TOKEN` | 否* | 按钮审批用的 GitHub Token（fine-grained PAT，需 Issues read/write 权限） |
| `PLUGIN_STORE_REPO` | 否 | 监听商店仓库，默认 `AxT-Team/AxTBot-PluginStore` |
| `PLUGIN_STORE_ADMIN_OPENIDS` | 否 | 允许操作审批按钮的管理员 openid（逗号分隔），留空不做成员校验 |

\* 用不到 Actions 推送 / 按钮审批功能时可留空。

示例：

```env
PLUGIN_STORE_GITHUB_SECRET=your_github_webhook_secret
PLUGIN_STORE_ACTIONS_TOKEN=your_actions_token
PLUGIN_STORE_GROUP_OPENID=your_group_openid
PLUGIN_STORE_GITHUB_TOKEN=ghp_xxx
PLUGIN_STORE_REPO=AxT-Team/AxTBot-PluginStore
PLUGIN_STORE_ADMIN_OPENIDS=
```

## 接线

### 1. GitHub 官方 Webhook

仓库 → **Settings → Webhooks → Add webhook**：

- **Payload URL**：`https://<AxTBot公网域名或IP>:<AxTBot端口>/notify/github-webhook`
- **Content type**：`application/json`
- **Secret**：与 `PLUGIN_STORE_GITHUB_SECRET` 保持一致
- **Which events**：**Let me select individual events** → 勾选 **Issues**

### 2. GitHub Actions 推送

商店仓库的 `plugin-submission.yml` / `update-plugin-versions.yml` 会推送到
`AUTO_REVIEW_WEBHOOK_URL`。在仓库 **Settings → Secrets and variables → Actions** 配置：

- `AUTO_REVIEW_WEBHOOK_URL` = `https://<AxTBot公网域名或IP>:<AxTBot端口>/notify/actions-webhook`
- `AUTO_REVIEW_WEBHOOK_TOKEN` = 与 `PLUGIN_STORE_ACTIONS_TOKEN` 一致

### 3. QQ 开放平台

- 机器人需开启**群聊消息（markdown）**与**消息按钮**能力；
- 事件订阅回调地址指向 AxTBot 的 `/webhook`（框架已配置，无需改动）；
- `/webhook`（QQ 回调）与 `/notify/*`（本插件）共用同一端口，路径不同，不冲突。

### 4. 公网可达

本插件不单独监听端口，直接复用 AxTBot 主服务端口。确保 AxTBot 主端口通过
frp / 反向代理对外可达（GitHub Webhook、Actions 推送、QQ 回调共用该端口）。

## 事件类型

Actions 推送的 `event` 字段支持以下类型：

| event | 触发动作 |
|---|---|
| `plugin_review_required` | 自动验证未通过，推「人工审核」通知（含通过/拒绝按钮） |
| `plugin_approved` | 自动验证通过，推「已合入」通知 |
| `plugin_version_check` | 每日版本检查结果 |

## 开发

```bash
pdm install --dev
pdm run format       # isort + black 格式化
```

代码规范：Python ≥ 3.11，`black`（line-length 90）+ `isort` 配置见 `pyproject.toml`。

## 构建发布

```bash
pdm build            # 输出到 dist/
pip install dist/axtbot_plugin_store_notify-*.whl
```

## 常见问题

**Q：重启后日志里没看到 `notify >>> 已挂载`？**

确认插件是否被加载（日志应出现 `插件 >>> 从本地包/PyPI 加载插件: 插件商店通知`）。
本地包方式请检查 `plugins/axtbot_plugin_store_notify/` 目录是否完整。

**Q：GitHub Webhook 返回 401？**

`local.env` 的 `PLUGIN_STORE_GITHUB_SECRET` 与 GitHub Webhook 配置的 Secret 不一致。

**Q：Actions 推送被 401 拒收？**

`local.env` 的 `PLUGIN_STORE_ACTIONS_TOKEN` 与仓库 Actions Secret `AUTO_REVIEW_WEBHOOK_TOKEN`
不一致，或该项未配置。
