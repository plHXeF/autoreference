# 机器接口 1.0

以下命令均通过 `python <skill目录>/scripts/run.py` 调用。所有参数文件为 UTF-8 JSON。命令输出一份 JSON，包含 `schema_version`、`operation`、`status` 和 `data` 或 `error`。退出码 1 表示输入或执行错误；成功、部分成果和需要用户操作通过 JSON 状态区分。日志只写标准错误。

## 准备与读取

`task prepare --input paper.docx --output task-dir` 或 `--text "论断"`，两者选一个。任务目录必须专用于此输入；相同输入再次 prepare 返回已有任务，不清除进度。正文、论断 ID 和已有参考文献位于 `data.document`。现有引用的原键位于 `existing_references[].key`。

`task inspect task-dir` 返回全任务；`task inspect task-dir --claim-id c_...` 返回此论断、候选和证据。任务状态保存于 `task-dir/task.json`，不要直接编辑它。异常退出留下 `task.lock` 时，先确认原进程已退出，再删除该锁文件。

## 检索

`task search task-dir --requests queries.json [--refresh]`

```json
{"requests":[{"claim_id":"c_...","queries":["shifted windows cross window connections"],"limit":8}]}
```

每批 1–20 项、每项 1–6 个查询，limit 为每源每查询 1–25 条。可显式设置 `sources:["openalex","crossref","anysearch","zhizhen"]`；省略时使用公共源，只有设置 `ANYSEARCH_API_KEY` 才默认加入 AnySearch。无配置的源标记 `unconfigured`。相同请求复用已有结果，`--refresh` 才重试。

结果以 `data.candidates` 保存，由候选 ID 索引；`claim_candidates` 对应论断与候选，`search_runs` 保留每源结果和失败状态。并发最多 4 个请求，校园查询串行。临时网络错误/限流最多请求 3 次，每次退避不超过 5 秒。

## 核验与补充实际读取的证据

`task verify task-dir [--references extracted.json] [--evidence evidence.json]`

extracted.json 为从原有未结构化引用中提取的字段，key 必须已存在，字段必须实际出现在原文：

```json
[{"key":"1","title":"Original paper title","authors":["Jane Doe"],"year":2021,"doi":"10.1234/example"}]
```

有 DOI 时核对 Crossref；无 DOI 时要求题名、年份和作者匹配，题名相同本身不足以核验。原始裸引用不能可靠分出题名时留作未解决项，不能把整个字符串假设为论文标题。`conflicts` 记录历史来源差异；核验成功时这些差异可由权威元数据解释并标记 `resolution:authoritative-metadata`，修正记录于 `metadata_changes`。实质身份核验冲突由 `metadata_status:conflict` 表示，不能进入新增推荐集。

evidence.json 只收录实际读取的摘要或全文段落，不收录猜测内容：

```json
[{"candidate_id":"p_...","url":"https://publisher.example/paper","kind":"abstract","text":"Actual content read from the source."}]
```

外部证据标记 `agent_supplied`，工具只检查引用指向和片段一致性，不独立证明该段内容来自此页面。数据库返回的摘要标记 `provider`。返回的 `data.evidence` 提供 evidence ID。新增候选未核验或存在核验冲突时不能进入推荐集。

## 判断与导出

`task finalize task-dir --decisions decisions.json`

```json
{
  "decisions":[{"claim_id":"c_...","candidate_id":"p_...","support":"supported","reason":"The evidence directly states the mechanism under the same conditions.","evidence_id":"e_...","quote":"Actual content read from the source"}],
  "skipped_claims":{"c_other":"Original result; no external citation needed."}
}
```

support 为 `supported/uncertain/unsupported`。supported 要求 evidence ID 指向此候选，quote 为证据中逐字一致的有效片段。其他状态不要求片段。工具的形式检查不能替代你的语义判断。

每次提交合并判断，相同论断—候选对的新判断覆盖旧判断。`decisions:[]` 保留已有判断。同一批不能同时跳过和评估同一论断；后续提交新判断会解除旧跳过，提交跳过会移除该论断的旧判断。

输出 `references.bib`、`report.json`、`report.md`，不覆盖非本任务管理的同名文件。JSON 报告的 `citation_keys` 对应最终引用键，保留已有键并处理新键冲突。已核验的旧 BibTeX 按权威元数据补齐/修正标准字段，保留非标准附加字段并记录变化；未核验条目保留原字段。新文献必须是 supported 且 metadata_status=verified；旧引用可保留 unverified 状态。recommended[].origin 区分 existing/new，new_reference_count 是去重后的实际新增文献数。未解决论断或原有文献导致 partial 状态。

## 访问与诊断

`doctor` 检查依赖和配置存在性，不联网、不显示密钥。新任务不读取或调用模型 API Key。

`access status` 返回缓存状态和浏览器依赖是否存在，不证明会话仍然有效。`access login --timeout 180` 开启专用浏览器，等待用户手动登录并进入知真检索结果页，最后关闭浏览器并保存专用会话。超时不自动重试。`access reset` 只清除工具管理的会话目录。

配置通过环境变量传入，或在启动时读取本地 `.env`：`ANYSEARCH_API_KEY`、`OPENALEX_API_KEY`、`AUTOREFERENCE_CONTACT_EMAIL`、`AUTOREFERENCE_CAMPUS_LOGIN_URL`、`AUTOREFERENCE_ACCESS_DIR`、`AUTOREFERENCE_CHROME_BINARY`、`AUTOREFERENCE_CHROMEDRIVER`。登录资料不得进入任务参数、报告、版本库或聊天记录。
