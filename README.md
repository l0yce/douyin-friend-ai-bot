# 抖音白名单好友 AI 自动回复机器人

运行在 Linux 服务器上的抖音网页版私信机器人。它只处理配置在白名单中的私聊对象；登录、会话定位、身份核验、生成回复和发送均由本项目本地执行。

> 抖音没有提供个人私信自动回复的官方接口。本项目通过浏览器操作网页版抖音，网页改版、登录失效、风控或网络异常都可能使功能停止。请只用于知情且信任的联系人，低频使用；不要用于群发、营销或陌生人骚扰。

## 核心安全规则

机器人不是只按昵称回复。每次处理消息前，必须同时通过三项精确校验：

1. 会话列表标题与白名单 `name` 一致；
2. 会话行绑定的 `sec_uid` 与白名单 `sec_uid` 一致；
3. 打开会话后读取到的公开抖音号 `douyin_id` 与白名单 `douyin_id` 一致。

任意一项缺失、读不到或不一致，机器人都会跳过该会话，不读取消息、不调用 AI、不发送回复。`sec_uid` 是抖音分配的长字符串内部身份标识；公开抖音号可能修改，`sec_uid` 用于稳定绑定会话对象。

运行日志会记录成功核验，例如：

```text
[44075411366] 身份核验通过：会话 sec_uid 与白名单一致；读取抖音号 44075411366 与白名单一致
```

审计日志会保存 `verified_douyin_id` 和布尔值 `verified_sec_uid`，便于复查；不会写入完整 `sec_uid`。

## 功能

- 白名单私聊自动回复；非白名单会话、核验失败会话一律跳过。
- 文字消息生成短文本回复；可选视觉模型用于图片消息。
- 已处理消息指纹、防重复回复、每好友每小时/每天上限、随机轮询和发送间隔。
- `--dry-run` 演练模式：读取和生成，但不发送。
- 浏览器故障现场保存截图和 HTML；回复和决策写入 JSONL 审计日志。
- 独立的白名单发现脚本，可输出含 `name`、`douyin_id`、`sec_uid` 的可复制配置项。

机器人只发送文字，不会发送图片、表情、卡片或执行支付、抢红包等操作。默认跳过无法可靠读取内容的语音、卡片等非文本消息。

## 环境与目录

在兼容的 Linux 服务器上运行。首次部署前由部署脚本自动检查所需环境。

- 以 `root` 执行首次部署脚本。
- Python 3.11、Xvfb、Firefox 与 Python 依赖由部署脚本准备。
- 浏览器使用项目目录中的 `ms-playwright/` Firefox；服务器会自动启动 Xvfb 虚拟显示。
- 项目当前目录：`/www/wwwroot/douyin-friend-ai-bot`

```text
.
├── config/config.json                   # 私密配置：AI、登录路径、白名单
├── deploy/douyin-friend-ai-bot.service  # systemd 服务模板
├── scripts/setup_linux.sh                # Linux 环境准备
├── scripts/discover_friends.sh           # 只读发现白名单身份
├── src/
│   ├── main.py                           # 命令行入口
│   ├── runner.py                         # 主循环、回复与审计
│   ├── douyin_chat.py                    # 会话操作和身份核验
│   ├── browser_manager.py                # Firefox、Xvfb、Cookie/登录态
│   ├── config_loader.py                  # 配置加载与严格校验
│   └── page_selectors.py                 # 抖音页面选择器
├── state/                                # Cookie、浏览器 profile、去重状态（私密）
├── logs/                                 # 运行、审计和故障现场日志（私密）
└── ms-playwright/                        # Playwright Firefox 运行时
```

不要公开 `config/config.json`、`state/`、`logs/` 或 `ms-playwright/`。

## 首次部署

在项目目录执行：

```bash
cd /www/wwwroot/douyin-friend-ai-bot
bash scripts/setup_linux.sh
```

脚本会安装 Python 3.11、Xvfb 和 Firefox 运行库，创建或复用 `.venv`，安装 `requirements.txt`，下载 Firefox，并检查 Firefox 能否启动。若旧虚拟环境不兼容，会先移动为带时间戳的 `.venv.backup-...`，不会直接删除。

完成后检查：

```bash
.venv/bin/python src/main.py --config config/config.json --check-login
```

## 登录抖音

推荐在自己的电脑浏览器登录抖音网页版后，用 Cookie-Editor 导出 Cookie JSON，再安全地上传到服务器。例如：

```bash
cd /www/wwwroot/douyin-friend-ai-bot
.venv/bin/python src/main.py --config config/config.json --import-cookie /安全位置/cookies.json
.venv/bin/python src/main.py --config config/config.json --check-login
```

导入后 Cookie 保存到 `state/cookies.json`。Cookie 等同登录凭证，不要发给他人、截图或提交仓库。Cookie 失效后重新导出并覆盖导入即可。

也支持 `--login-qr` 扫码登录，但它需要可见图形界面；服务器场景通常使用 Cookie 导入更方便。

## 配置

配置文件为 `config/config.json`。程序会给缺失的普通配置项补默认值，但启动正式机器人时，每位启用白名单好友都必须有 `name`、`douyin_id` 和 `sec_uid`。

最小结构示例（不要覆盖已有真实配置中的 API Key 和登录设置）：

```json
{
  "owner": {
    "douyin_id": "你的公开抖音号",
    "nickname": "可选"
  },
  "whitelist": {
    "exact_match": true,
    "friends": [
      {
        "name": "聊天列表显示的名字",
        "douyin_id": "对方公开抖音号",
        "sec_uid": "MS4wLjAB...",
        "enabled": true
      }
    ]
  },
  "ai": {
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "你的密钥",
    "model": "deepseek-chat",
    "vision_model": ""
  }
}
```

| 区块 | 关键字段 | 说明 |
| --- | --- | --- |
| `owner` | `douyin_id` | 建议填写自己的公开抖音号，用于排除误识别到本人。 |
| `whitelist.friends` | `name` | 左侧会话列表的精确显示名/备注。 |
|  | `douyin_id` | 对方公开抖音号。 |
|  | `sec_uid` | 与会话行绑定的内部身份标识，由发现脚本获取，不要猜测或手填。 |
|  | `enabled` | `false` 时忽略该项。 |
| `ai` | `base_url`、`api_key`、`model` | OpenAI 兼容接口的地址、密钥与文字模型。 |
| `ai` | `vision_model` | 可选；填写支持图片输入的模型时可处理图片消息。 |
| `reply` | `max_per_friend_per_hour`、`max_per_friend_per_day` | 单个好友的回复上限。 |
| `poll` | `cycle_min_seconds`、`cycle_max_seconds` | 轮询间隔范围。 |
| `account` | `profile_dir`、`cookies_file` | 浏览器 profile 与 Cookie 文件路径；通常无需修改。 |

不要把自己的 `owner.douyin_id` 填入白名单；校验会拒绝这种配置。

### 家庭网络代理

#### 为什么需要稳定的家庭/运营商出口

本项目的运行经验是：未使用稳定的家庭/运营商网络出口、或浏览器出口频繁变化时，抖音网页版更容易出现以下现象：私信面板加载异常、消息无法发送、要求重新登录或安全验证，表现为原有 Cookie 不能继续使用。它们是网络环境、浏览器 profile、Cookie 连续性和操作频率共同作用的结果，并不是“换了 IP 就必然失效”的公开规则；家庭代理也不能保证登录态永久有效。

因此，建议浏览器长期固定走同一个稳定的家庭/运营商出口，避免在运行期间切换代理、在服务器公网出口与代理出口之间来回切换，或多人共享同一浏览器 profile。Cookie 应在与服务器相同的稳定出口环境下导入并持续使用；如果出现安全验证或登录失效，重新导入 Cookie 后先运行 `--check-login`，确认通过再恢复自动回复。

#### 当前项目如何使用代理

浏览器启动时会读取 `config/config.json` 的 `account.proxy_server`，并将该代理传给 Playwright 的 Firefox 持久化浏览器上下文。因此抖音网页、私信页面和发送动作都经此代理访问。AI 接口调用由 Python `httpx` 单独发起，不使用这个浏览器代理。

当前服务器配置的是本地 SOCKS5 入口（例如 `socks5://localhost:1080`）；本地代理服务再转发到家庭/运营商出口。若你的代理服务在其他机器，改成对应的 SOCKS5 或 HTTP(S) 地址即可：

```json
"account": {
  "proxy_server": "socks5://用户名:密码@代理地址:端口"
}
```

没有认证信息时可写为 `socks5://代理地址:端口`。代理地址、用户名和密码属于私密凭据，不要写进 README、运行日志、截图或公开仓库。

#### 启动前与故障后的检查

```bash
cd /www/wwwroot/douyin-friend-ai-bot

# 使用当前浏览器配置检查登录态
.venv/bin/python src/main.py --config config/config.json --check-login

# 不发送消息地走一轮流程
.venv/bin/python src/main.py --config config/config.json --dry-run --once

# 实时查看浏览器、代理与登录相关日志
tail -f logs/runtime.log
```

运行日志出现 `NS_ERROR_PROXY_CONNECTION_REFUSED`，说明 Firefox 在访问或刷新页面时被代理拒绝连接。项目曾记录过这种短暂错误：定时刷新失败后，后续轮询继续执行并恢复；如果该错误持续出现，不要直接启动正式回复。先检查本地代理服务是否运行、代理出口是否稳定，再运行 `--check-login`。若登录态复查失败，重新导入 Cookie。

| 现象 | 优先处理方式 |
| --- | --- |
| `NS_ERROR_PROXY_CONNECTION_REFUSED` | 检查本地 SOCKS5/HTTP 代理服务、端口和上游出口；恢复后执行 `--check-login`。 |
| 页面能打开但私信无法发送或面板空白 | 停止正式运行，确认代理出口未切换；用 `--dry-run --once` 复现并查看 `runtime.log`。 |
| 提示登录失效或安全验证 | 停止机器人，在稳定出口下重新导出/导入 Cookie，然后 `--check-login`。 |
| 代理正常但仍反复异常 | 保留 `logs/runtime.log` 与 `logs/screenshots/` 现场；不要删除 `state/browser_profile_firefox`，避免丢失同设备连续性。 |

> 不要把代理当作规避平台规则的手段。它的作用是保持浏览器网络环境的一致性；仍应低频、谨慎运行，并接受平台可能要求重新验证的情况。

## 新增白名单好友

先让对方至少给该账号发过一条私信，使会话出现在左侧列表。然后运行独立脚本：

```bash
cd /www/wwwroot/douyin-friend-ai-bot
bash scripts/discover_friends.sh
```

该脚本是只读模式：**不会调用 AI，也不会发送消息**。它会逐个读取最近会话，并对可安全添加的对象输出：

```text
可复制白名单项：{"name":"小明","douyin_id":"xiaoming123","sec_uid":"MS4wLjAB...","enabled":true}
```

将整段 JSON 放入 `config/config.json` 的 `whitelist.friends` 数组，例如：

```json
"friends": [
  { "name": "已有好友", "douyin_id": "old_id", "sec_uid": "MS4w...", "enabled": true },
  { "name": "小明", "douyin_id": "xiaoming123", "sec_uid": "MS4wLjAB...", "enabled": true }
]
```

如果输出显示“未能获取”或“不能添加到严格白名单”，不要手填 `sec_uid`；让对方重新发私信后再运行脚本。群聊不应加入白名单。

## 常用命令

所有命令均在项目根目录运行：

```bash
cd /www/wwwroot/douyin-friend-ai-bot

# 检查登录态
.venv/bin/python src/main.py --config config/config.json --check-login

# 仅列出当前会话标题
.venv/bin/python src/main.py --config config/config.json --list-conversations

# 发现可加入白名单的会话（推荐使用独立脚本）
bash scripts/discover_friends.sh

# 测试 AI，只生成一句话，不发送
.venv/bin/python src/main.py --config config/config.json --test-ai "在吗"

# 整链路演练：会读取/判断/生成，但不发送
.venv/bin/python src/main.py --config config/config.json --dry-run --once

# 仅运行一轮并实际发送符合规则的回复
.venv/bin/python src/main.py --config config/config.json --once

# 持续运行；Ctrl+C 停止
.venv/bin/python src/main.py --config config/config.json
```

首次实际使用前，先执行 `--dry-run --once`。确认日志中出现完整的“身份核验通过”记录后，再启动实际发送。

## systemd 常驻运行

确认手动运行无误后安装服务：

```bash
cd /www/wwwroot/douyin-friend-ai-bot
cp deploy/douyin-friend-ai-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now douyin-friend-ai-bot
```

服务文件默认使用当前项目目录 `/www/wwwroot/douyin-friend-ai-bot`。如果移动项目，先同步修改服务文件中的 `WorkingDirectory`、`ExecStart` 和 `PLAYWRIGHT_BROWSERS_PATH`。

常用管理命令：

```bash
systemctl status douyin-friend-ai-bot
systemctl restart douyin-friend-ai-bot
systemctl stop douyin-friend-ai-bot
journalctl -u douyin-friend-ai-bot -f
```

## 日志、状态与排查

| 文件或目录 | 内容 |
| --- | --- |
| `logs/runtime.log` | 启动、登录、身份核验、跳过原因、异常。 |
| `logs/reply_audit.jsonl` | 每个决策/演练/回复的 JSONL 审计记录；成功核验项含 `verified_douyin_id` 与布尔值 `verified_sec_uid`，不保存完整 `sec_uid`。 |
| `logs/screenshots/` | 点开会话或页面异常时的截图和 HTML。 |
| `state/` | Cookie、Firefox profile、已处理消息状态。删除会要求重新登录或丢失去重状态。 |

实时查看身份核验：

```bash
tail -f logs/runtime.log
```

常见情况：

- **登录失效/安全验证**：重新导出 Cookie，执行 `--import-cookie`，再 `--check-login`。
- **白名单启动时报缺字段**：使用 `bash scripts/discover_friends.sh` 获取完整配置项；每项必须含 `name`、`douyin_id`、`sec_uid`。
- **“核验不符”而不回复**：这是安全保护。核对聊天列表显示名、公开抖音号与 `sec_uid`；不要通过删除校验绕过。
- **Firefox 启动失败**：重新运行 `bash scripts/setup_linux.sh`，查看其缺失库提示与 `logs/runtime.log`。
- **无回复**：先用 `--dry-run --once` 检查是否有未读、是否是文字消息、是否命中频率/去重限制，以及身份核验是否通过。

## 更新项目后

更新源码后执行：

```bash
cd /www/wwwroot/douyin-friend-ai-bot
bash scripts/setup_linux.sh
.venv/bin/python -m py_compile src/*.py
systemctl restart douyin-friend-ai-bot
```

更新前保留 `config/`、`state/` 和 `logs/`；它们包含私密登录态、白名单和审计记录。
