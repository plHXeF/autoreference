# 验收记录：0.2.0a0

日期：2026-10-08（Asia/Shanghai）。实际运行平台为 macOS / Apple Silicon，Python 3.13.0。

## 修改前备份与版本

原分支 `main`、原提交 `9251a73ca3bc0d9be466c9d75030a99111f04a82`，重构前工作区干净。先备份，后建立标签和分支，未修改原稿。

- 备份：`backups/autoreference-before-skill-20261008-181353.tar.gz`
- 大小：218,204,633 bytes
- 验证：7,934 个文件、目录与符号链接；逐文件 SHA-256 核对压缩内容与原文件，并核对符号链接目标及范围完整性。
- SHA-256：`ccf18ebef25b9206f1baaf25a588850e36657df43c6ecf1336164c695f73c434`
- 校验文件和逐文件清单位于备份旁；备份目录权限 0700，文件权限 0600。
- 原版本标签：`pre-skill-20261008-9251a73`
- 重构分支：`codex/skill-refactor`；分阶段本地提交，未合并、推送或配置远程。

## 自动与真实运行验证

| 项目 | 结果 |
|---|---|
| 原有 CLI、服务、Web、模型 API 离线回归 | 通过；模型调用使用模拟传输 |
| 全部自动测试 | 54 项通过 |
| Ruff 静态检查 | 通过 |
| skill-creator 的 quick_validate | 通过 |
| TXT/DOCX/TEX 解析、引用字段、脚注/表格、包含文件、循环/缺失、原稿不变 | 通过 |
| 无模型依赖的真实隔离安装与三格式处理 | 通过；doctor 显示 web/llm/campus 均未安装 |
| 实际安装、更新、卸载及含空格路径 | 通过；卸载保留用户资料 |
| 安装失败回滚、手动修改保护、目录所有权 | 自动测试通过 |
| 原键保留、中文、特殊字符、卷期页、BibTeX 解析 | 通过，使用 bibtexparser 检查输出 |
| 缺 DOI 匹配、不同 DOI 不合并、冲突和元数据变更 | 通过 |
| 伪造片段、未核验/不支持候选、不受管理输出文件 | 按预期拒绝 |
| 校园登录、缓存状态、403、跳过/失败及公共回退 | 模拟测试通过；未真实登录 |
| OpenAlex / Crossref 在线冒烟 | 两源均返回候选；BERT 原论文核验成功 |
| AnySearch JSON/Markdown、鉴权/格式错误 | 模拟测试通过；未联网验收 |
| Windows/Linux 与 Python 3.11 | 配置 CI 矩阵，尚未实际执行 |

唯一现有测试警告来自新版 Starlette 对 httpx TestClient 的弃用提示，不影响断言；后续依赖升级可处理。

## 独立 agent 验收

独立 agent 只获得已安装 skill 和 TXT/DOCX/TEX 三份小论文，使用 skill 的机器接口、通用 Python 和公共学术 API。没有模型 API Key、校园访问或 Codex 专属功能，没有直接编辑任务状态或源码。

三份论文都完成 prepare → search → verify → 实际阅读证据 → finalize，每份导出一条已核验的 BERT 原论文，并保留原引用键。该论文已经存在于输入参考文献中，实际新增独立文献为 0。

数据库的“abstract”字段在本例中只是书目信息，agent 没有据此确认支持；它实际读取 ACL 出版页面的摘要，记录来源后判断支持。这验证了证据不足时的公共页面补充流程。

首次验收发现新增计数、历史差异说明和已有 BibTeX 补齐问题，已修复并由同一独立 agent 重新验收：三格式均为 success，会议、页码和链接补齐，变更可追溯。无关候选的未核验状态保留在报告中。

本地成果：`.skill-test/acceptance-final/{txt,docx,tex}/references.bib`，各目录附 Markdown/JSON 报告。原始查询、响应与独立验收报告只保存在被 Git 忽略的本地目录；发布包不包含它们。

## 尚未验证与边界

真实校园 SSO、校园网/VPN、Chrome 驱动和机构 DOM 必须在对应环境另行验收。当前没有进行账号登录。AnySearch 实时鉴权和响应尚未验证。跨平台 CI 尚未运行，没有进行 LaTeX 编译或真实 Word 渲染。

通用安装和 JSON 接口已经实现，但任意宿主 agent 的发现机制、命令执行权限和推理质量不能由单一环境验证保证。支持范围明确为能读取 skill、执行 Python 并联网的 agent。复杂 Word 引用字段、TeX 宏和非 Crossref 注册 DOI 可能需要人工或 agent 复核。

不将多源命中、元数据核验或片段一致性检查解释为独立证明论断。当前仍为 alpha。
