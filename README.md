# AutoReference

[![Checks](https://github.com/plHXeF/autoreference/actions/workflows/tests.yml/badge.svg)](https://github.com/plHXeF/autoreference/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A portable agent skill that turns claims and TXT, DOCX, or TEX manuscripts into verified BibTeX references. No model API key required.

为一句论断或 TXT、DOCX、TEX 论文整理参考文献、补找支持文献并返回 BibTeX。当前版本：**0.2.0a0**。

用户安装 skill 后，可以向支持本地命令的 agent 说：

> 为这篇论文整理已有参考文献，并为缺少引用的论断补找文献，返回 BibTeX。

宿主 agent 负责理解正文、生成检索词和判断支持程度；本地工具负责解析文件、检索、核验、去重和导出。基础流程不要求模型 API Key，也不依赖 Codex 专属工具。

## 安装 skill

需要 Python 3.11+、联网能力，以及能够读取 `SKILL.md`、执行本地命令的 agent。

推荐从 [GitHub Releases](https://github.com/plHXeF/autoreference/releases) 下载 `autoreference-skill-0.2.0a0.zip`，解压后进入目录运行安装器。发布包已包含固定版本 wheel。

也可以获取源码：

```sh
git clone https://github.com/plHXeF/autoreference.git
cd autoreference
```

从仓库或解压后的发布包运行：

```sh
python scripts/install_skill.py --skill-dir "/your/agent/skills/autoreference"
```

目标必须是该 agent 能发现的 skill 目录。实际操作流程见 [SKILL.md](skills/autoreference/SKILL.md)。安装器创建独立运行环境，安装固定版本 AutoReference，并复制 skill 和启动脚本。无现成 wheel 时，仓库安装会先构建 wheel。安装过程会下载 Python 依赖；调用 skill 时不会临时安装。安装完后，让 agent 重新发现 skill。

启用可选校园访问：

```sh
python scripts/install_skill.py --skill-dir "/your/agent/skills/autoreference" --with-campus
```

更新、诊断和卸载：

```sh
python scripts/install_skill.py --skill-dir "/your/agent/skills/autoreference" --update
python "/your/agent/skills/autoreference/scripts/run.py" doctor
python scripts/install_skill.py --skill-dir "/your/agent/skills/autoreference" --uninstall
```

更新不会覆盖手动修改的 skill 文件；失败保留原运行环境。卸载仅移除安装器管理的文件和运行环境，保留用户资料。不要手动移动安装后的虚拟环境；更换路径时重新安装。

Windows 使用可用的 `python`；macOS/Linux 可将示例中的 `python` 换成 `python3`。命令支持含空格的路径。

## 输出与推荐标准

- `references.bib`：已有可可靠解析的参考文献，以及核验后具有证据支持的新增推荐。
- `report.json`：候选、来源、元数据核验、证据、agent 判断、引用键映射、失败记录和未解决项。
- `report.md`：可阅读的结果和论断对应报告。

已有 BibTeX 保留原引用键，核验后补齐或修正标准字段并记录变更；未核验条目保留原字段并标注状态。未结构化引用需要 agent 从原文提取真实字段后核验，无法可靠识别的内容不猜补。新增文献必须核验书目元数据，并由 agent 提供实际证据片段和支持判断。

多源匹配、书目核验、论断支持是不同状态。工具校验引用指向和片段一致性，不能独立证明 agent 的语义判断正确。标题相似或引用量高不代表文献支持论断。

不会修改原论文，也不会自动插入引用。未解决项导致部分成功状态；没有合格新增文献时不虚构条目。

## 文档与数据源

支持直接输入文本和 `.txt`、`.docx`、`.tex`。DOCX 提取正文、表格、脚注/尾注及可识别的 CSL 引用字段；未知字段报告警告。TEX 读取项目内包含文件、BibTeX 和内嵌参考文献，检测循环和缺失文件，不编译、不执行 TeX、不读取项目外文件。

默认 OpenAlex、Crossref。配置 `ANYSEARCH_API_KEY` 后加入 AnySearch Academic，支持 JSON 和 Markdown 响应。知真为实验性可选数据源。

仅必要的检索词、题名或 DOI 发送到学术接口，不将整篇论文发送给数据库。任务和报告仍可能包含研究资料，请妥善保管。

## 配置和校园访问

配置通过环境变量或运行目录下的 `.env` 提供。参考 [.env.example](.env.example)。

| 配置 | 用途 |
|---|---|
| `ANYSEARCH_API_KEY` | 启用 AnySearch |
| `OPENALEX_API_KEY` | 可选 OpenAlex Key |
| `AUTOREFERENCE_CONTACT_EMAIL` | 公共 API 联系邮箱 |
| `AUTOREFERENCE_CAMPUS_LOGIN_URL` | 用户学校的登录入口 |
| `AUTOREFERENCE_ACCESS_DIR` | 专用浏览器会话目录 |
| `AUTOREFERENCE_CHROME_BINARY` / `AUTOREFERENCE_CHROMEDRIVER` | 可选浏览器位置 |

默认使用公共来源。用户指定校园源，或关键证据受限且已配置访问方式时，skill 才介入校园访问。用户自行输入账号、密码和验证码，或连接校园网/VPN；工具不收集密码、不读取日常浏览器 Cookie、不绕过访问限制。

```sh
python "/your/agent/skills/autoreference/scripts/run.py" access status
python "/your/agent/skills/autoreference/scripts/run.py" access login --timeout 180
```

登录后在专用浏览器进入知真检索结果页，工具才能确认访问成功。登录超时、跳过、无浏览器或仍失败时，继续公共来源并报告缺口。403 本身不能确定是账号、校园网还是服务端问题。`access reset` 清除专用会话。

需要 Chrome 和可用的 Selenium 驱动；未指定驱动时 Selenium Manager 可能需要下载驱动。基础流程无需浏览器。

## 独立 Python 包与旧入口

```sh
python -m pip install -e "."
autoreference search "需要引用支持的论断" --no-llm
autoreference paper paper.txt --no-llm --output output
```

旧 `paper` 命令保留原来纯文本逐句处理行为。三种格式和宿主 agent 流程使用新的 `task` 接口；详细 JSON 协议见 [protocol.md](skills/autoreference/references/protocol.md)。

WebUI 和独立模型 API 为可选依赖：

```sh
python -m pip install -e ".[web,llm]"
autoreference web
```

WebUI 默认监听 `127.0.0.1:8000`，没有公网认证系统。旧模型 API 流程仍通过环境变量配置；新 `task` 流程即使配置了模型 Key 也不会调用模型服务。

## 开发、打包与验证

```sh
python -m venv .runtime
# 使用当前平台的激活方式，或直接调用该环境里的 Python。
python -m pip install -e ".[dev]"
pytest
ruff check src tests scripts skills/autoreference/scripts main.py utils.py
python scripts/build_release.py
```

发布包位于 `dist/autoreference-skill-0.2.0a0.zip`，只包含 skill、安装器、wheel 和说明，不包含备份、凭据或论文资料。开发测试使用模拟 API，不消耗模型费用；在线检索、真实校园登录和跨平台安装另行验收。

[架构说明](docs/architecture.md) · [验收记录](docs/validation.md)

## 版本与恢复

重构前完整版本保存在本地 `backups/`，附 SHA-256 和逐文件验证清单；Git 标签 `pre-skill-20261008-9251a73` 指向原提交。备份包含被 Git 忽略的资料，因此只在本地保存，不进入发布包或版本库。

源码、skill、测试和安装器由 Git 管理；运行环境、浏览器会话、原稿、报告和备份均被忽略。当前仍为 alpha：校园访问与平台兼容性以验收记录为准。本项目采用 [MIT License](LICENSE)，允许使用、修改和分发；依赖库仍遵循各自许可证。

## 项目结构

| 路径 | 内容 |
|---|---|
| `skills/autoreference/` | 可发布的 skill、跨平台启动器及 JSON 接口说明 |
| `src/autoreference/` | 文档解析、检索、核验、任务、访问会话和导出实现 |
| `scripts/` | 独立环境安装器、发布打包和安装验收 |
| `tests/` | 原有功能回归与新流程测试 |
| `docs/` | 架构和验收范围 |

欢迎通过 GitHub Issues 报告可复现问题。提交样例前请去除未公开论文、凭据及个人信息。
