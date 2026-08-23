const form = document.querySelector("#search-form");
const submitButton = document.querySelector("#submit-button");
const resultSection = document.querySelector("#result-section");
const resultList = document.querySelector("#result-list");
const warningsBox = document.querySelector("#warnings");
const querySummary = document.querySelector("#query-summary");
const resultCount = document.querySelector("#result-count");
const selectedCount = document.querySelector("#selected-count");
const runtimeStatus = document.querySelector("#runtime-status");

let candidates = [];
const selected = new Set();

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function updateSelectedCount() {
  selectedCount.textContent = `已选 ${selected.size} 篇`;
}

function scoreClass(score) {
  if (score >= 70) return "score-high";
  if (score >= 40) return "score-medium";
  return "score-low";
}

function renderQueries(queries) {
  querySummary.replaceChildren();
  [...(queries.chinese || []), ...(queries.english || [])].forEach((query) => {
    querySummary.append(element("span", "query-chip", query));
  });
}

function renderWarnings(warnings) {
  warningsBox.replaceChildren();
  if (!warnings.length) {
    warningsBox.hidden = true;
    return;
  }
  warningsBox.hidden = false;
  warnings.forEach((warning) => warningsBox.append(element("div", "", warning)));
}

function metadataText(candidate) {
  const parts = [];
  if (candidate.authors?.length) parts.push(candidate.authors.slice(0, 4).join(", "));
  if (candidate.authors?.length > 4) parts.push("等");
  if (candidate.year) parts.push(candidate.year);
  if (candidate.journal) parts.push(candidate.journal);
  if (candidate.doi) parts.push(`DOI ${candidate.doi}`);
  return parts.join(" · ") || "来源未返回完整书目信息";
}

function renderCandidate(candidate, index) {
  const card = element("article", "result-card");
  const selection = element("label", "select-candidate");
  selection.setAttribute("aria-label", `选择 ${candidate.title}`);
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = selected.has(index);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) selected.add(index);
    else selected.delete(index);
    updateSelectedCount();
  });
  selection.append(checkbox);

  const body = element("div", "candidate-body");
  body.append(element("p", "candidate-source", candidate.source));
  const title = element("h3", "candidate-title");
  if (candidate.url) {
    const link = element("a", "", candidate.title);
    link.href = candidate.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    title.append(link);
  } else {
    title.textContent = candidate.title;
  }
  body.append(title);
  body.append(element("p", "metadata", metadataText(candidate)));
  body.append(
    element(
      "p",
      "abstract",
      candidate.abstract || "该数据源没有返回摘要；请打开原文后再判断是否可引用。",
    ),
  );
  const assessment = candidate.assessment || {};
  body.append(element("p", "assessment-reason", assessment.reason || "尚未评估"));
  if (assessment.caveats?.length) {
    const list = element("ul", "caveats");
    assessment.caveats.forEach((item) => list.append(element("li", "", item)));
    body.append(list);
  }

  const scoreBox = element("div", "score-box");
  const score = Number(assessment.relevance_score || 0);
  scoreBox.append(element("span", `score ${scoreClass(score)}`, String(score)));
  scoreBox.append(element("span", "score-label", " / 100 相关度"));
  card.append(selection, body, scoreBox);
  return card;
}

function renderResults(data) {
  candidates = data.candidates || [];
  selected.clear();
  candidates.forEach((candidate, index) => {
    if (candidate.assessment?.can_cite && candidate.assessment.relevance_score >= 70) {
      selected.add(index);
    }
  });
  resultCount.textContent = `${candidates.length} 篇候选文献`;
  renderWarnings(data.warnings || []);
  renderQueries(data.queries || {});
  resultList.replaceChildren();
  if (!candidates.length) {
    resultList.append(element("p", "empty-state", "没有找到候选结果。可以缩短论断或更换检索源。"));
  } else {
    candidates.forEach((candidate, index) => {
      resultList.append(renderCandidate(candidate, index));
    });
  }
  updateSelectedCount();
  resultSection.hidden = false;
  resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const sources = [...document.querySelectorAll('input[name="source"]:checked')].map(
    (node) => node.value,
  );
  if (!sources.length) {
    window.alert("请至少选择一个检索源。");
    return;
  }
  submitButton.disabled = true;
  submitButton.firstElementChild.textContent = "正在检索与评估…";
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        claim: document.querySelector("#claim").value.trim(),
        sources,
        max_results_per_source: Number(document.querySelector("#limit").value),
        use_llm: document.querySelector("#use-llm").checked,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "检索失败");
    renderResults(data);
  } catch (error) {
    resultSection.hidden = false;
    renderWarnings([error.message]);
    resultList.replaceChildren();
  } finally {
    submitButton.disabled = false;
    submitButton.firstElementChild.textContent = "搜索候选引用";
  }
});

document.querySelectorAll("[data-export]").forEach((button) => {
  button.addEventListener("click", async () => {
    const chosen = candidates.filter((_, index) => selected.has(index));
    if (!chosen.length) {
      window.alert("请先选择至少一篇候选文献。");
      return;
    }
    const format = button.dataset.export;
    const response = await fetch(`/api/export/${format}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidates: chosen }),
    });
    if (!response.ok) {
      window.alert("导出失败，请稍后重试。");
      return;
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `autoreference.${format === "bibtex" ? "bib" : format}`;
    link.click();
    URL.revokeObjectURL(link.href);
  });
});

fetch("/api/health")
  .then((response) => response.json())
  .then((data) => {
    runtimeStatus.classList.add("ready");
    runtimeStatus.textContent = data.llm_enabled
      ? `${data.judge_model} · reasoning ${data.reasoning_effort}`
      : "公开检索模式 · 未配置 AI Key";
  })
  .catch(() => {
    runtimeStatus.textContent = "服务状态不可用";
  });

