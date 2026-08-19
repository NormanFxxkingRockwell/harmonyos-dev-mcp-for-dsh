# harmonyos-dev-mcp-for-dsh

![license](https://img.shields.io/badge/license-Apache--2.0-green)
![dsh](https://img.shields.io/badge/dsh-plugin-4B32C3)
![python](https://img.shields.io/badge/python-3.12+-blue)
[![Awesome DSH Plugin](https://awesome-dsh-plugin.com/badge.svg)](https://awesome-dsh-plugin.com)

**@deepseek-ai/dsh 插件：把 `harmonyos-dev-mcp`（HarmonyOS 设备 MCP 服务）桥接进 DeepSeek Harness**。
安装后，AI 助手直接获得一套完整的鸿蒙开发工具：设备发现、构建/安装/启动/卸载、UI 自动化（点击/输入/按键/截图）、E2E 检查（UI 树/窗口/元素等待）、日志验证（错误提取/业务标记/历史日志/崩溃解析）。

## 工作原理

本插件是标准 dsh-plugin（`dsh.bundle.patch` → `cordis.patch.yml` 插入一行 host 插件），**零 npm 依赖**：

```
cordis.patch.yml
  └─> id: harmonyos-dev-mcp (本包 lib/index.js)
        ├─ 1. 解析 Python 运行时（bundled .venv → uv run 项目环境 → 系统 python）
        ├─ 2. 拉起服务器并完成 MCP 握手（失败给出可修复提示，含服务器 stderr 尾部；不影响 profile 启动）
        └─ 3. 以内嵌的轻量 MCP stdio 客户端（newline-delimited JSON-RPC）调用
              ├─ 18 个工具以 mcp__harmonyos__<tool> 注册到 ctx.tools
              └─ 崩溃监督：指数退避自动重启并重新同步工具（上限 5 次）
```

只使用 Node 内置模块与宿主服务（`ctx.tools` / `ctx.systemPrompt`），不依赖任何 npm 包，
避免把 @deepseek-ai/* 重复安装到 profile 造成符号不一致（会破坏宿主工具调度器）。

Python 源码完整打包在本仓库（`src/`、`pyproject.toml`、`uv.lock`）；**首次激活会自动用
`uv` 按 lockfile 准备 Python 环境（需联网一次，之后秒级）**，环境目录固定在
`$DSH_HOME/plugin-envs/harmonyos-dev-mcp`，不写入 pnpm store。

## 安装

环境要求（宿主机）：

- Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)（推荐，自动管理项目环境）
- HarmonyOS SDK 工具链（`hdc`、DevEco Studio 5.0+），与官方 `harmonyos-dev-mcp` 要求一致

```sh
# 方式一（推荐）：npm registry 安装（发布后即用，无任何拦截）
dsh plugin --profile <你的profile> add harmonyos-dev-mcp-for-dsh
dsh plugin --profile <你的profile> update harmonyos-dev-mcp-for-dsh   # 升级

# 方式二：GitHub 源码安装（免发布，可固定到 tag）
dsh plugin --profile <你的profile> add github:NormanFxxkingRockwell/harmonyos-dev-mcp-for-dsh#v0.1.0

# 方式三：本地 checkout（开发）
dsh plugin --profile <你的profile> add file:<本仓库路径>
```

GitHub 源安装时 pnpm 会拦截 git 包的 prepare 脚本：按提示把输出的 key 加入
`<profile>/pnpm-workspace.yaml` 的 `allowBuilds` 后重跑即可（该 key 锁定 commit
hash，**用 `#v0.1.0` 固定 tag 后 key 不会随推送变动**；该脚本只做 uv 缓存预热，
跳过也不影响运行）。

重启 profile 后，在对话里直接说「列出连接的鸿蒙设备 / 安装这个 hap / 查看某应用界面 / 查最近错误日志」，
模型会自动调用工具。

## Release

正式发布走 npm registry（`npm publish`，包名 `harmonyos-dev-mcp-for-dsh`，见 `package.json` 的
`dsh.bundle.patch` 声明，`dsh plugin add` 会自动把它挂载为 profile bundle 层）。
GitHub 仓库同步打 tag（如 `v0.1.0`）供 `github:#tag` 方式固定版本。

## 工具清单（18 个，命名空间 mcp__harmonyos__）

| 类别 | 工具 |
|---|---|
| 通用 | `list_devices`、`query_package`（list/abilities/main_ability/permissions）、`logs_query`（errors/markers） |
| 构建部署 | `build_app`（hap/har/hsp/app/hnp + HSP 集成）、`install_app`、`run_app`（自动探测入口并验证窗口）、`uninstall_app` |
| UI 自动化 | `screenshot`、`click`、`long_press`、`input_text`（IME 安全策略）、`swipe`、`drag`、`press_key`（354 个 KEYCODE）、`find_elements` |
| E2E | `get_ui_tree`、`list_windows`、`wait_for_element`（严格 deadline） |

设备目标参数：`device_id?`（`hdc list targets`）与 `hdc_server?`（无线调试 `IP:port`）；
也可用环境变量 `HARMONYOS_HDC_SERVER` 设置默认无线端点。
**`build_app` 是长任务：插件默认把单次 tool 调用超时设为 300s**（可通过配置调整）。

详细参数、结果字段、错误码、示例见 [docs/tool_reference.md](docs/tool_reference.md) 与 [docs/logs_query.md](docs/logs_query.md)。

## 配置（可选）

在 profile 的 `cordis.patch.yml` 里按 id 覆盖：

```yaml
- id: harmonyos-dev-mcp
  config:
    pythonPath: C:\Path\To\.venv\Scripts\python.exe   # 显式指定 python（跳过自动解析）
    # uvPath: C:\Path\To\uv.exe                       # 显式指定 uv
    # useUv: false                                     # 禁用 uv 解析（改用系统 python）
    # envDir: D:\cache\hm-env                         # uv 项目环境目录（默认 $DSH_HOME/plugin-envs/harmonyos-dev-mcp）
    # serverName: hm                                  # 工具命名空间（默认 harmonyos -> mcp__harmonyos__*）
    # toolCallTimeoutMs: 300000                        # 单次工具调用超时
    # connectTimeoutMs: 120000                         # 服务器握手/首次环境准备预算（慢网络可调大）
    # env:
    #   HARMONYOS_HDC_SERVER: 192.168.43.34:35215     # 默认无线端点
```

Python 运行时解析顺序：

1. `config.pythonPath`（显式）
2. 插件包内 `.venv`（`uv sync` 创建的开发环境）
3. `uv run --project <本包>`，且 `UV_PROJECT_ENVIRONMENT` 固定到
   `$DSH_HOME/plugin-envs/harmonyos-dev-mcp`（避免污染 pnpm store）
4. 系统 `python`（需已 `pip install harmonyos-dev-mcp`）

启动失败不会拖垮 profile：会记录错误日志，并在系统提示中说明修复方式。

## 验收 / 排障

```sh
# 一键检查：运行时解析 + import probe + MCP 握手 + tools/list
node node_modules/harmonyos-dev-mcp-for-dsh/bin/check.js

# 加 --device：还会对 hdc 真机跑 list_devices / query_package / logs_query / get_ui_tree
node node_modules/harmonyos-dev-mcp-for-dsh/bin/check.js --device
```

常见问题：

- 工具没出现：先跑 `bin/check.js`；确认 profile 已重启；确认日志无 `[harmonyos-dev-mcp]` 错误。
- `mcp__harmonyos__*` 调用报连接错误：真机是否连接（`hdc list targets`）、无线端点是否正确。
- `build_app` 超时：确认 `toolCallTimeoutMs >= 120000`，冷构建建议 300s。
- `find_elements` 按 `element_id` 找不到：ArkUI 组件的 `.id()` **不会**出现在 uitest 的
  ID 字段（那是 accessibilityId）；请改按 `text` 或 `element_type`（如 `Button`/`TextInput`/`ListItem`）查找。
- 截图打不开 / vision 报「Declared image type does not match its bytes」：
  `screenshot` 的设备端 `snapshot_display` 只会产出 **JPEG** 字节（上游行为），
  无论 `local_path` 是什么后缀。请让模型把截图保存为 `.jpg`/`.jpeg` 路径
  （或拿到 `.png` 文件后改名再交给 vision / read_image）。

## 本地开发

```sh
uv sync            # 准备 Python 环境
uv run pytest tests/unit -v            # 上游单测（295 个）
node bin/check.js --device --verbose   # 端到端验收
```

## 与上游的关系

本仓库 fork 自 [Deslord319/harmonyos-dev-mcp](https://github.com/Deslord319/harmonyos-dev-mcp)（Apache-2.0），
在其之上增加了 dsh-plugin 外壳（`package.json` / `cordis.patch.yml` / `lib/` / `bin/`），
Python 服务本体与文档原样保留。

## License

Apache License 2.0（见 [LICENSE](LICENSE)）