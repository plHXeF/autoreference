# AutoReference

> **Pre-release / 未完整实测：`0.1.0a0`**  
> 核心逻辑具备离线单元测试；OpenAlex、Crossref 已在 2026-09-07 完成实时请求冒烟测试；
> 知真搜索页及校园机构识别已验证，但无头浏览器的 SSO 偶发 403，尚不能视为稳定可用。
> 使用任何候选引用前，必须人工核对摘要和原文。

AutoReference 是一个面向论文写作的候选引用搜索工具。输入一句需要证据支持的论断，它会：

1. 生成适合学术数据库的中英文检索词（可选）；
2. 并行查询 OpenAlex、Crossref，以及实验性的知真数据源；
3. 去重并整理题目、作者、年份、摘要、DOI 等书目信息；
4. 用 reasoning 模型保守评估“这篇文献是否真的能支撑这句话”；
5. 由用户选择后导出 BibTeX、CSV 或 JSON。

它的定位是“可能引用的搜索引擎”，不是自动证明生成器。模型没有看到的原文不会被假装读过；
摘要缺失或证据不足时应进入人工复核，而不是自动插入论文。

## 当前状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| WebUI | 可用，离线导入已验证 | 本机 FastAPI + 原生前端 |
| CLI 单句检索 | 可用，离线逻辑已验证 | 支持 JSON 输出和 BibTeX 导出 |
| CLI 整篇处理 | 可用，离线逻辑已验证 | 输出完整候选报告，不修改原稿 |
| OpenAlex | 模拟测试及实时冒烟测试通过 | 2026-09-07 返回有效候选结果 |
| Crossref | 模拟测试及实时冒烟测试通过 | 2026-09-07 返回有效候选结果 |
| OpenAI Responses API | 已按当前接口实现 | 需要用户自己的 Key 才能端到端测试 |
| 知真 | **部分验证** | 搜索页与当前 DOM 已核验；无头 Chrome 的校园 SSO 偶发 403 |

## 与旧原型相比

- Key 只从环境变量读取，源码和示例配置中不包含真实密钥；
- 默认使用稳定的公开学术 API，不再依赖 Google Scholar 页面抓取；
- 使用 Responses API 和结构化输出，支持 reasoning effort；
- 一次批量评估候选文献，不再对每个结果单独调用模型；
- 缺摘要时采取保守策略，不允许仅凭“主题看起来相似”就自动放行；
- 浏览器驱动路径不再硬编码，知真插件使用 Selenium Manager 或用户显式配置；
- 提供 CLI、WebUI、标准 CSV/BibTeX/JSON 导出、离线测试和断言明确的发布状态。

旧的论文正文、缓存、生成结果和内置 Chrome 均保留在本地，但已写入 `.gitignore`，不会进入新仓库。

## 安装

需要 Python 3.11 或更高版本。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

如果需要试验知真数据源：

```powershell
python -m pip install -e ".[zhizhen,dev]"
```

知真不是默认源。未安装 Selenium 时，OpenAlex 和 Crossref 不受影响。

## 配置

编辑本地 `.env`：

```dotenv
OPENAI_API_KEY=你的密钥
AUTOREFERENCE_OPENAI_BASE_URL=https://api.openai.com/v1
AUTOREFERENCE_QUERY_MODEL=gpt-5.6-luna
AUTOREFERENCE_JUDGE_MODEL=gpt-5.6-terra
AUTOREFERENCE_REASONING_EFFORT=auto
AUTOREFERENCE_API_MODE=responses
```

`.env` 已被 Git 忽略。不要把 Key 写入 Python、README、命令历史或截图。

### Reasoning 预算

默认 `AUTOREFERENCE_REASONING_EFFORT=auto` 是按任务自适应的：

- 检索词扩展使用 `low`，因为任务明确且高频；
- 引用支撑判断使用 `high`，因为误配引用的代价更高；
- 检索词和判断分别预留 4,000 与 12,000 个最大输出 token，包含模型的 reasoning token。

可以显式设为 `none`、`low`、`medium`、`high`、`xhigh` 或 `max`。`max` 适合质量优先的困难论断，
但延迟和费用会显著增加，并且要求所选模型实际支持该档位。默认模型采用当前 GPT-5.6 系列：
查询侧偏向成本，判断侧平衡质量与成本。若你希望质量优先，可将判断模型改为 `gpt-5.6`。

OpenAI 官方建议 reasoning 工作流使用 Responses API，并显式设置 effort：
[Model guidance](https://developers.openai.com/api/docs/guides/latest-model)。

### 第三方 OpenAI-compatible 端点

可设置 `AUTOREFERENCE_OPENAI_BASE_URL` 和模型名。若服务商尚未实现 Responses API：

```dotenv
AUTOREFERENCE_API_MODE=chat_completions
```

兼容模式会使用 Chat Completions、JSON object 和 `reasoning_effort` 扩展字段。不同服务商的字段、
模型名和实际思考预算可能不同，需要按服务商文档验证；项目不会假设其行为与 OpenAI 完全一致。

### 公共学术 API 礼貌池

建议填写联系邮箱：

```dotenv
AUTOREFERENCE_CONTACT_EMAIL=you@example.com
AUTOREFERENCE_USER_AGENT=AutoReference/0.1 (mailto:you@example.com)
```

## WebUI

```powershell
autoreference web
```

打开 <http://127.0.0.1:8000>。界面支持：

- 输入单条论断；
- 选择检索源、结果数量和是否启用 AI 评估；
- 阅读摘要、评分依据和风险提示；
- 手动勾选候选文献；
- 导出 BibTeX、CSV 或 JSON。

交互式 API 文档位于 <http://127.0.0.1:8000/docs>。

默认只监听 `127.0.0.1`。这个版本没有登录和权限系统，不要直接把服务暴露到公网。

## CLI

搜索一句话：

```powershell
autoreference search "Swin Transformer 使用移位窗口建立跨区域上下文" --limit 8
```

不使用 LLM，只做公开检索和本地粗排：

```powershell
autoreference search "core image analysis for ore grade prediction" --no-llm
```

输出 BibTeX：

```powershell
autoreference search "masked autoencoder for geological imagery" --bibtex candidates.bib
```

整篇处理：

```powershell
autoreference paper paper.txt --output output --minimum-score 70
```

整篇处理会生成：

- `output/citation_candidates.json`：每个句子的全部候选、评分和警告；
- `output/references.bib`：模型明确判为可引用且达到阈值的保守集合。

它不会修改原始论文，也不会自动把 `\\cite{}` 插回正文。

## 数据流

```text
论断/论文
   │
   ├─ 可选 reasoning 模型：生成中英文检索词
   │
   ├─ OpenAlex / Crossref / 实验性知真
   │
   ├─ DOI + 规范化标题去重
   │
   ├─ 本地相似度粗排
   │
   ├─ 可选 reasoning 模型：批量保守评估
   │
   └─ 人工选择 → BibTeX / CSV / JSON
```

## 测试

离线测试不会访问学术 API，也不会调用 LLM：

```powershell
pytest
ruff check .
```

发布前仍需要在具备相应凭据和网络条件的环境中完成：

1. OpenAlex、Crossref 实时查询冒烟测试；
2. OpenAI Responses API 的结构化输出测试及费用/延迟评估；
3. 至少一组人工标注论断—文献数据上的准确率评估；
4. 校园网或机构访问环境中的知真页面、登录态和 DOM 选择器测试；
5. Chrome、Chromedriver 与 Selenium Manager 在目标平台的兼容性测试。

## 安全、隐私与研究诚信

- 论文论断会发送给所选学术 API；启用 AI 时也会发送给配置的模型服务商。
- 不要提交包含未公开研究、个人信息或保密数据的全文，除非你接受相应服务商的数据政策。
- `relevance_score` 是辅助排序信号，不是“文献真实支持该论断”的证明。
- DOI、年份、作者和 BibTeX 仍应与出版社页面或原文核对。
- 不应引用只看过标题、摘要不支持原句、已经撤稿或无法确认来源的文献。

## 已知限制

- 当前不读取 PDF/Word，也不识别原稿中已有的引用；输入是 UTF-8 纯文本或单句。
- OpenAlex/Crossref 的摘要覆盖率并不完整。
- 没有付费数据库的统一登录、Cookie 导入或代理配置。
- 没有 DOI 内容协商或撤稿状态校验。
- 中文分句和中英文混排虽比旧版保守，仍需要在真实论文上继续评估。
- 暂未选择开源许可证；对外公开前请由仓库所有者补充合适的 `LICENSE`。

## 版本约定

当前版本为 `0.1.0a0`，其中 `a` 表示 alpha。只有在实时 API、模型调用和知真环境完成验证后，
才建议移除 README 顶部的未测试声明并发布稳定版本。
