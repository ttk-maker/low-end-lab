# Qwen 中文乐理问答：本机配置

本项目为作者个人及贝斯爱好者交流的非盈利兴趣项目。当前功能使用百炼 API，非盈利用途不免除提供商的按量调用费用。

## 先开通服务

1. 登录阿里云百炼／模型服务控制台，按平台要求开通服务及模型权限。
2. 在与你的业务空间、地域对应的位置创建 API Key。不要把 Key 发到聊天、截图、前端代码或共享压缩包。
3. 打开 [Qwen-Omni 官方文档](https://help.aliyun.com/zh/model-studio/qwen-omni)，找到当前账号适用的 **Chat Completions base_url**。本版默认模型为 `qwen3.8-omni-flash`，不要把开源模型名称或 Realtime 地址填入。
4. 地址应为官方 `https://…aliyuncs.com/compatible-mode/v1`。使用文档中的业务空间地址时，必须把 `{WorkspaceId}` 替换为实际值；不直接保留占位符。API Key 与地址的地域需对应。

## 在这台电脑配置

**Windows 推荐直接使用下面的配置工具，不需要运行 `export`，也不需要安装 Bash 或 WSL。** `export NAME=value` 是 Bash 等 shell 的语法，不能直接用于 PowerShell 或 CMD。此前说明没有给出 Windows 的环境变量语法，现补充如下。

双击上级目录的 `配置Qwen问答.cmd`：先粘贴服务地址，再输入 API Key。Key 输入不显示在屏幕上。配置工具不会主动发送收费请求。

配置保存到整个交付目录的上一级 `work/private/qwen.json`，不在 HTTP 静态文件根目录内，也不包含在共享 ZIP 中。它是本机可读的明文配置，不是系统凭据保险库；不要分享 `work/private` 目录。拥有你本机文件访问权限的人可以读到它。

也支持后端环境变量 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_BASE_URL`，环境变量优先于文件；可选 `LOWEND_QWEN_MODEL` 指定模型标识。变量方式更改后需重新启动服务；配置文件方式在下一次请求时读取。

运行 `启动音频分析.cmd`，打开工作台，点击“和 Astra 聊乐理”中的“检查本机配置”。“已配置”只表示本地字段齐全；账号权限、额度和实际接口兼容性要到首次真实请求才会验证。

## Windows 环境变量方式（可选，与配置工具二选一）

### PowerShell

通常提示符以 `PS` 开头。下面的命令在本机终端执行，服务地址按自己账号的官方文档填写。Key 使用隐藏输入，避免把它直接写进命令历史。

```powershell
$env:DASHSCOPE_BASE_URL = Read-Host '粘贴官方 Chat Completions base_url'
$qwenSecureKey = Read-Host '输入 API Key（隐藏）' -AsSecureString
$env:DASHSCOPE_API_KEY = [System.Net.NetworkCredential]::new('', $qwenSecureKey).Password
Remove-Variable qwenSecureKey

# 只检查是否有值，不输出 Key。
[bool]$env:DASHSCOPE_API_KEY
[bool]$env:DASHSCOPE_BASE_URL
```

两项都应为 `True`。这些变量仅在当前 PowerShell 及其之后启动的子进程中生效，关闭窗口后不会永久保存。要使用它们，请先在原服务窗口按 Ctrl+C 停止服务，再在设置变量的同一个 PowerShell 中启动：

```powershell
& 'C:\Users\jj183\Documents\Codex\2026-11-07\astra-agent-agent-agent-jam-1\outputs\启动音频分析.cmd'
```

若项目已移动，请修改路径。不要仅在资源管理器中重新双击启动脚本：它不会继承这个 PowerShell 的临时变量。启动脚本检测到已有服务时只会打开网页，不会重启服务或更新它的环境变量；刷新浏览器也不会更新后端进程的环境。

**已经输入临时变量，却仍显示“尚未配置”时，推荐直接保存为项目配置。** 在刚才输入 `$env:` 命令的同一个 PowerShell 窗口执行：

```powershell
& 'C:\Users\jj183\Documents\Codex\2026-11-07\astra-agent-agent-agent-jam-1\outputs\配置Qwen问答.cmd' --from-env
```

看到 `Saved outside the shared outputs folder` 后，回网页点击“检查本机配置”。这会将该终端的 Key、地址和可选模型名保存到项目的私有配置文件，不显示 Key、不调用模型；原服务没有环境变量覆盖时即可直接读到。如果提示 Key 或地址为空，说明这个终端没有完整变量，原配置不会被覆盖，请直接双击配置工具重新输入。该工具也可修复格式损坏的旧配置文件。

### CMD（命令提示符）

CMD 使用 `set "变量名=值"`，而不是 `export` 或 `$env:`。例如：

```bat
set "DASHSCOPE_BASE_URL=替换为官方服务地址"
```

Key 变量的语法相同，但直接输入会显示在屏幕上。建议在 CMD 中直接运行 `配置Qwen问答.cmd`，使用其隐藏 Key 输入及持久配置功能。`set` 也是当前窗口临时生效；`setx` 修改的是以后启动的进程环境，无法更新已经运行的服务，因此这里不推荐用 `setx` 排查问题。

### 配置后仍显示未配置或认证失败

1. 采用配置工具时，回工作台点击“检查本机配置”；文件配置每次请求都会重新读取，通常无需重启。
2. 采用环境变量时，确认从同一个终端重新启动了后端服务，而不是只刷新页面。
3. 环境变量优先于配置文件。如果服务启动时带着旧 Key 或旧地址，重新运行配置工具不会覆盖进程中的旧变量。停止旧服务后，可在启动服务的 PowerShell 中执行以下命令，清除该终端的覆盖，再从该终端启动服务使用文件配置：

```powershell
Remove-Item Env:DASHSCOPE_API_KEY, Env:DASHSCOPE_BASE_URL, Env:LOWEND_QWEN_MODEL -ErrorAction SilentlyContinue
& 'C:\Users\jj183\Documents\Codex\2026-11-07\astra-agent-agent-agent-jam-1\outputs\启动音频分析.cmd'
```

这不会删除用户或系统永久变量，也不会删除已保存的配置文件。不要使用输出整个环境变量表的命令来排错或发送截图，以免显示 Key。

## 如何提问

- 一般乐理问题：直接输入“为什么小七和弦可以用三音和七音构成贝斯线？”等问题，点击“向 Qwen 提问”。
- 针对当前和弦：先回听、确认并保存和弦，再勾选“使用当前已确认并保存的和弦作为依据”。后端会重新读取保存版本，拒绝过期或未确认事件。
- 当前发送内容为文字问题、最多四张知识卡，以及可选的已确认和弦区间、构成音。**不发送音频，也不能宣称模型听过原曲。**
- 回答属于模型建议，知识卡仍有待教师复核。页面显示实际返回的 Token 用量（若接口提供）与可查阅的知识来源。

## 费用与失败

按 [官方计费页](https://help.aliyun.com/zh/model-studio/model-pricing)和实际账号地域执行。配置工具不计模型调用费；点击提问会调用 API。相同模型、问题与依据的成功响应在本次服务进程内缓存；重启会清空。失败不自动重试，避免不可见的重复调用。

401 通常是 Key 无效，403 是权限或地域不符，404 是地址或模型不存在，429 是配额或频率限制。接口返回的原始错误正文不会回显，以避免意外暴露配置。连接失败时不会回退到伪造模型回答。

### 地址与认证故障排查（2026-11-08）

服务地址必须完整复制，不能将完整域名再次拼到地域后缀上。例如 `ws-示例.cn-beijing.maas.aliyuncs.com.cn-beijing.maas.aliyuncs.com` 是错误域名；`cn-beijing.maas.aliyuncs.com` 只应出现一次。新版配置工具会拒绝重复后缀，并将 HTTPS 域名／证书错误、DNS 错误和超时分别提示，始终保留证书校验。

“本机配置已就绪”只代表字段齐全。若后续出现 HTTP 401，请在百炼控制台的 API Key 管理中核对或新建对应地域／业务空间的 Key，复制完整 Key 后重新运行配置工具。不要填入阿里云 AccessKey ID、AccessKey Secret、工作空间 ID 或模型名称。地址修正后仍报 401 时，不应继续增加超时时间。

## 当前验证边界

本次用户尚未开通 Key，故只完成了本地配置流程、接口合同、流式响应解析、错误处理、缓存、依据校验和浏览器测试。离线测试中的模拟提供商响应不是真实 Qwen 推理，不能作为回答质量证据。首次真实连通、实际费用和中文音乐回答质量仍需配置后验证。
