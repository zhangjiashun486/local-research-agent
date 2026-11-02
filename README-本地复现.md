# 本地资料研究 Agent（开源二次开发实践）

> **2026-10-26 更新：** 中英文报告、受控网页工具、正文去重复与上下文预算、原文摘录和读取日志已补齐。本轮 103 项 pytest 通过。另一台电脑更新和启动请看 [更新说明](docs/更新说明-20261026.md)。下方 10 月 14 日改动数量与测试数量保留为历史记录，当前功能以本更新说明为准。

一个通过本地模型整理指定网页、生成带来源报告的小应用。提供程序直接读取和模型调用网页工具两种模式，支持中英文界面/新报告、Markdown 下载与 SQLite 历史留存。当前指定来源路径不再为了凑轮数重复读取同一批网页；自动全网搜索和完整浏览器操作不在已验收范围内。

- 技术栈：Python 3、LangGraph、本地大模型（OpenAI 兼容接口）、FastAPI、SQLite、JSON Schema、pytest
- 演示形态：本地网页界面 + REST 接口；不依赖付费 API
- 最近一次真实链路验证：2026-10-14，指定Python官方typing文档，1轮完成；报告副本见 `docs/sample-report-20261014.md`。10月13日原报告也保留。

## 上游与许可

- 上游项目：langchain-ai/local-deep-researcher，提交 `03537326ffa0dd90c9702bece2f3aeba5d84162a`，MIT。
- 上游 Git 拉取被连接重置，改用 GitHub 源码压缩包导入；真实提交号与压缩包 SHA-256 见 `UPSTREAM.json`。
- 本地 Git 的第一个提交是**上游快照**（`2d8e49d`，标注 not personal contribution），之后的 `d2c970b` 才是本项目的二次开发改动；`git diff 2d8e49d d2c970b` 可直接看到全部差异。

## 二次开发改动清单（相对上游）

初始二次开发批次修改/新增 18 个文件（`git diff --stat 2d8e49d d2c970b`：+467 / −17）。

| 方向 | 文件 | 做了什么 |
| --- | --- | --- |
| 研究流程与预算 | `src/ollama_deep_researcher/graph.py` | 检索预算 off-by-one 修正（原用 `<=` 判断，导致"上限 1 轮"实际跑 2 次）；新增 `search_status` 三态，失败或空结果直接收敛，不再拿空结果去总结；无有效来源时不生成无引用结论 |
| 本地模型适配 | `src/ollama_deep_researcher/lmstudio.py`、`configuration.py` | 适配本机 OpenAI 兼容接口（`/v1`）：改用 `json_schema` 结构化输出、修复扁平 `ChatResult` 访问、超时与最大输出长度可配置 |
| 来源与输出 | `src/ollama_deep_researcher/utils.py`、`state.py` | 新增指定 HTTPS 来源抓取（拒绝 file://、localhost、内网地址）；清洗思考前缀后再解析 JSON |
| 应用与接口 | `local_app/api.py`、`research.py`、`index.html`、`scripts/run_local.py` | 新增 FastAPI：`POST /research`、`GET /reports`、`GET /reports/{id}`、`/download`、`/docs`；SQLite 记录成功与失败、错误原因、轮数与耗时；本地网页界面 |
| 测试 | `tests/test_research_flow.py`、`test_local_api.py`、`test_provided_sources.py`、`test_local_model_adapter.py` | 新增 18 个用例，覆盖见"验证记录" |
| 依赖与说明 | `requirements-local.lock.txt`、`pyproject.toml`、`.gitignore` | 锁定可复现的本地依赖版本 |

## 从单独下载的仓库运行（Windows PowerShell）

前置：Python 3.11或以上，以及已安装并提供 OpenAI 兼容 HTTP API 的本地模型服务。
项目不会下载模型权重，也不会自动调用付费模型。请在本地模型软件中加载自己的模型、启用 API，记下 `/v1` 地址与模型ID。

在本仓库根目录执行；以下环境都在仓库内，不要求父目录已有虚拟环境或配置文件：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
Copy-Item -LiteralPath .\local-model-connection.example.json -Destination .\local-model-connection.json
```

编辑 `local-model-connection.json`：`base_url` 填本机API地址（默认 `http://127.0.0.1:1235/v1`），
`model` 必须把 `YOUR_LOADED_MODEL_ID` 换成该服务实际提供的模型ID。实际配置文件已被Git忽略，样例可以提交。
也可不创建JSON，直接在当前PowerShell设置：

```powershell
$env:LOCAL_RESEARCH_BASE_URL='http://127.0.0.1:1235/v1'
$env:LOCAL_RESEARCH_MODEL='这里替换为本机模型ID'
```

环境变量覆盖仓库内JSON；可用 `LOCAL_RESEARCH_CONFIG` 明确指定其他配置文件。
没有合法模型配置时，研究任务记录为 `failed` 并给出设置提示，而不是因找不到父目录文件抛出未处理异常。

```powershell
.\.venv\Scripts\python.exe -m uvicorn local_app.api:app --host 127.0.0.1 --port 8765
```

浏览器打开 `http://127.0.0.1:8765`，填写主题与来源网址并开始研究。首次建议用1轮及
`https://docs.python.org/3/library/typing.html`。`GET /health`只表示应用在线，不代表模型可用。
查看JSON中的 `status`、`actual_loops`、`error`，不要把HTTP 200当成研究成功。

已有本机环境可继续使用上级目录的 `启动AI项目.cmd`，但它是便捷入口，不是仓库运行的必要条件。

接口：`POST /research`、`GET /reports`、`GET /reports/{id}`、`GET /reports/{id}/download`、`GET /health`、`GET /docs`。

## 历史验证记录（2026-10-14）

**23 个自动化用例**（2026-10-14再次通过；在独立仓库可用 `.\.venv\Scripts\python.exe -m pytest tests` 复测）分五类：

| 类别 | 数量 | 覆盖内容 |
| --- | --- | --- |
| 研究流程图 | 11 | 预算严格按 1 轮 / 3 轮执行、非正预算被拒、空结果不产生无来源总结、超时与空结果区分、非法模型 JSON 回退（4 例）、思考前缀清洗 |
| 接口与持久化 | 4 | 主题过短与非法轮数被拒、未知报告返回 404、报告在连接重建后仍可读（SQLite 持久化）、缺少模型配置时失败记录可查询 |
| 来源模式 | 3 | 拒绝 `file://`、`localhost`、内网 IP 等非 HTTPS 来源 |
| 本地模型适配 | 1 | JSON Schema 结构化输出格式与扁平 `ChatResult` 解析 |
| 仓库独立配置 | 4 | 不读取父目录配置、无文件时用环境变量、环境覆盖JSON、缺少模型设置的明确提示 |

流程及接口用例使用**假的搜索响应与假的模型输出**，配置用例在独立临时目录中验证；它们不替代真实模型验收。**10月14日新增真实模型验收4项通过**：有效来源1轮报告、404来源失败且无事实总结、不可达来源失败、真实非JSON输出重放至实际解析方法得到主题回退值。第四项不是模型自然异常的完整研究链路；不可达域名本次实际遇到SSL EOF，不据此声称DNS超时已测。独立运行 `.\.venv\Scripts\python.exe scripts/verify_local_model.py`，结果写入 `outputs/checks/`；前三项还会保存报告与失败记录。该脚本只使用你配置的模型，本机验收使用已有免费本地模型。

产物与截图（都在本仓库内，可直接查看）：

- 最新真实报告副本：[`docs/sample-report-20261014.md`](docs/sample-report-20261014.md)。
- 10月13日真实报告副本：[`docs/sample-report-20261013.md`](docs/sample-report-20261013.md)（含 Sources 列表；原文件在本地 `outputs/`，该目录未纳入版本库）
- 界面与历史列表：[`docs/screenshots/ui-home.png`](docs/screenshots/ui-home.png)
- 报告全文（含来源）：[`docs/screenshots/sample-report-text.png`](docs/screenshots/sample-report-text.png)
- 接口实测记录：`<仓库外接口记录>`（仓库外）

## 当前限制（写在前面，避免误解）

- **自由网页搜索尚未跑通**：旧搜索包走 Bing 失败，换 ddgs 后 DuckDuckGo/Brave 仍未取到结果。当前可演示的是**指定来源网页研究**。
- 报告内容未逐条人工核实，不能当作事实来源；报告中的引用来自实际抓取的网页。
- 未接入付费搜索 API，未做 MCP、文档向量库或多 Agent 系统。

## 目录

```
src/ollama_deep_researcher/   上游包：graph.py（研究图）、lmstudio.py（本地模型）、utils.py（来源与清洗）
local_app/                    新增：FastAPI 接口、研究调用封装、网页界面
tests/                        23 个自动化用例
local-model-connection.example.json  本地模型配置样例（实际JSON不纳入版本库）
outputs/                      真实运行产出的报告（md/json）与 SQLite 历史库
UPSTREAM.json                 上游地址、提交号、压缩包校验值、许可证
requirements-local.lock.txt   锁定的本地依赖
```

## 责任与边界

本项目为实现与验证实践：选型、环境准备与结果验收由本人确认，实现与调试过程使用 AI 编码工具辅助。项目存在、测试通过均不等于本人已能独立编写全部源码；本文的改动清单与验证记录供后续独立复现与源码复习使用。

## 2026-10-14 配置独立性验证

源码复制到不含父目录配置的独立临时目录，复用已安装依赖，验证仓库内配置、HTTP接口、SQLite记录与下载；模型调用在该项检查中替换为固定结果。它验证配置和应用可搬移，不代表在另一台电脑重新安装依赖或真实模型端到端。详见本机 `.evidence/review-20261014/portable-smoke.json`。
