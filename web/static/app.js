const STEPS = ["Excel 配置", "文件匹配", "导入 OCR", "提取导出"];
let currentStep = 0;
let maxStep = 0;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.detail) {
    throw new Error(data.detail || `请求失败 ${res.status}`);
  }
  return data;
}

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2500);
}

// ---- stepper ----
function renderStepper() {
  const nav = document.getElementById("stepper");
  nav.innerHTML = "";
  STEPS.forEach((label, i) => {
    const dot = document.createElement("div");
    dot.className = "step-dot" + (i === currentStep ? " active" : i < currentStep ? " done" : "");
    dot.innerHTML = `<span class="num">${i + 1}</span> ${label}`;
    dot.onclick = () => goStep(i);
    nav.appendChild(dot);
  });
}

function goStep(i) {
  currentStep = i;
  maxStep = Math.max(maxStep, i);
  document.querySelectorAll(".step").forEach((s) => {
    s.hidden = Number(s.dataset.step) !== i;
  });
  renderStepper();
  if (i === 1) initMatch();
  if (i === 2) refreshOcrTable();
  if (i === 3) refreshExtractTable();
}

// ---- project ----
async function refreshState() {
  const s = await api("/api/state");
  document.getElementById("project-path").value = s.path || "";
  if (s.excel_name) document.getElementById("excel-name").textContent = s.excel_name;
  if (s.fields.length) renderFields(s.fields);
  if (s.match_rule.pattern) document.getElementById("pattern").value = s.match_rule.pattern;
  document.getElementById("mineru-token").value = s.mineru_token || "";
  document.getElementById("mineru-precision").checked = s.mineru_precision;
  document.getElementById("ocr-provider").value = s.ocr_provider || "mineru";
  document.getElementById("baidu-api-key").value = s.baidu_api_key || "";
  document.getElementById("baidu-secret-key").value = s.baidu_secret_key || "";
  onProviderChange();
  const llm = s.llm_config || {};
  document.getElementById("llm-url").value = llm.base_url || "http://localhost:11434/v1";
  document.getElementById("llm-key").value = llm.api_key || "";
  document.getElementById("llm-model").value = llm.model || "qwen2.5:7b";
}

async function newProject() {
  await api("/api/project/new", { method: "POST" });
  location.reload();
}
async function openProject() {
  const path = document.getElementById("project-path").value;
  try { await api("/api/project/open", { method: "POST", body: JSON.stringify({ path }) }); toast("已打开"); await refreshState(); }
  catch (e) { toast(e.message); }
}
async function saveProject() {
  const path = document.getElementById("project-path").value;
  try { const r = await api("/api/project/save", { method: "POST", body: JSON.stringify({ path }) }); document.getElementById("project-path").value = r.path; toast("已保存"); }
  catch (e) { toast(e.message); }
}

// ---- step 1 ----
async function uploadExcel() {
  const input = document.getElementById("excel-file");
  if (!input.files.length) return;
  const fd = new FormData();
  fd.append("file", input.files[0]);
  try {
    const res = await fetch("/api/excel/upload", { method: "POST", body: fd });
    const r = await res.json();
    if (!res.ok || r.detail) throw new Error(r.detail || "上传失败");
    document.getElementById("excel-name").textContent = input.files[0].name;
    renderFields(r.fields);
    toast(`加载 ${r.headers.length} 列`);
  } catch (e) { toast(e.message); }
}

function renderFields(fields) {
  const tb = document.querySelector("#fields-table tbody");
  tb.innerHTML = "";
  fields.forEach((f) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="checkbox" class="f-sel" ${f.selected ? "checked" : ""}></td>
      <td class="f-name">${f.name}</td>
      <td><input type="text" class="f-annot" value="${f.annotation || ""}"></td>
      <td><input type="text" class="f-ex" value="${(f.examples || []).join("、")}"></td>
      <td><input type="checkbox" class="f-ctx" ${f.is_context ? "checked" : ""}></td>`;
    tb.appendChild(tr);
  });
}

async function saveFields() {
  const fields = [...document.querySelectorAll("#fields-table tbody tr")].map((tr) => ({
    name: tr.querySelector(".f-name").textContent,
    annotation: tr.querySelector(".f-annot").value,
    examples: tr.querySelector(".f-ex").value.split("、").map((s) => s.trim()).filter(Boolean),
    is_context: tr.querySelector(".f-ctx").checked,
    selected: tr.querySelector(".f-sel").checked,
  }));
  await api("/api/fields", { method: "POST", body: JSON.stringify({ fields }) });
  toast("字段已保存");
  goStep(1);
}

// ---- step 2 ----
let selectedMatchFields = new Set();
async function initMatch() {
  const r = await api("/api/match/fields");
  const box = document.getElementById("match-fields");
  box.innerHTML = "";
  r.candidates.forEach((name) => {
    const chip = document.createElement("span");
    chip.className = "chip" + (selectedMatchFields.has(name) ? " on" : "");
    chip.textContent = name;
    chip.onclick = () => {
      if (selectedMatchFields.has(name)) { selectedMatchFields.delete(name); chip.classList.remove("on"); }
      else { selectedMatchFields.add(name); chip.classList.add("on"); }
    };
    box.appendChild(chip);
  });
}

async function uploadPdfs() {
  const input = document.getElementById("pdf-files");
  if (!input.files.length) return;
  const fd = new FormData();
  [...input.files].forEach((f) => fd.append("files", f));
  document.getElementById("pdf-name").textContent = "上传中...";
  try {
    const res = await fetch("/api/pdf/upload", { method: "POST", body: fd });
    const r = await res.json();
    if (!res.ok || r.detail) throw new Error(r.detail || "上传失败");
    document.getElementById("pdf-name").textContent = `已上传 ${r.count} 个文件`;
    toast(`已上传 ${r.count} 个 PDF`);
  } catch (e) { document.getElementById("pdf-name").textContent = "上传失败"; toast(e.message); }
}

async function previewMatch() {
  const body = {
    pattern: document.getElementById("pattern").value,
    match_fields: [...selectedMatchFields],
  };
  try {
    const r = await api("/api/match/preview", { method: "POST", body: JSON.stringify(body) });
    const tb = document.querySelector("#match-table tbody");
    tb.innerHTML = "";
    r.results.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><input type="checkbox" class="sel" data-row="${row.row_index}" ${row.matched ? "checked" : ""}></td>
        <td>${row.row_index}</td><td>${row.generated}</td>
        <td>${row.matched ? "✅ 已匹配" : "❌ 未匹配"}</td><td>${row.file_path}</td>`;
      tb.appendChild(tr);
    });
    toast(`匹配 ${r.results.filter((x) => x.matched).length}/${r.results.length}`);
  } catch (e) { toast(e.message); }
}

function toggleAll(tableId, val) {
  document.querySelectorAll(`#${tableId} tbody .sel`).forEach((cb) => (cb.checked = val));
}

async function saveSelected() {
  const rows = [...document.querySelectorAll("#match-table tbody .sel:checked")].map((cb) => Number(cb.dataset.row));
  await api("/api/match/selected", { method: "POST", body: JSON.stringify({ rows }) });
  toast(`已选 ${rows.length} 行`);
  goStep(2);
}

// ---- step 3 ----
function onProviderChange() {
  const provider = document.getElementById("ocr-provider").value;
  document.getElementById("mineru-config").hidden = provider !== "mineru";
  document.getElementById("baidu-config").hidden = provider !== "baidu";
}

async function saveMineru() {
  await api("/api/mineru/config", { method: "POST", body: JSON.stringify({
    provider: document.getElementById("ocr-provider").value,
    token: document.getElementById("mineru-token").value,
    precision: document.getElementById("mineru-precision").checked,
    baidu_api_key: document.getElementById("baidu-api-key").value,
    baidu_secret_key: document.getElementById("baidu-secret-key").value,
  })});
  toast("OCR 设置已保存");
}

async function refreshOcrTable() {
  const r = await api("/api/ocr/table");
  const tb = document.querySelector("#ocr-table tbody");
  tb.innerHTML = "";
  r.rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="checkbox" class="sel" ${row.selected ? "checked" : ""} disabled></td>
      <td>${row.row_index}</td><td>${row.file_name}</td>
      <td>${row.status}</td><td>${row.page_count}</td><td>${row.error}</td>`;
    tr.onclick = () => showOcrPreview(row.row_index);
    tb.appendChild(tr);
  });
}

async function showOcrPreview(rowIndex) {
  const r = await api(`/api/ocr/preview/${rowIndex}`);
  document.getElementById("ocr-preview").textContent = r.markdown.slice(0, 3000);
}

async function startOcr() {
  try {
    const r = await api("/api/ocr/start", { method: "POST" });
    pollJob(r.job_id, "ocr-progress", refreshOcrTable);
  } catch (e) { toast(e.message); }
}

// ---- step 4 ----
async function saveLlm() {
  await api("/api/llm/config", { method: "POST", body: JSON.stringify({
    base_url: document.getElementById("llm-url").value,
    api_key: document.getElementById("llm-key").value,
    model: document.getElementById("llm-model").value,
  })});
  toast("LLM 设置已保存");
}

async function refreshExtractTable() {
  const r = await api("/api/extract/table");
  const tb = document.querySelector("#extract-table tbody");
  tb.innerHTML = "";
  r.rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${row.row_index}</td><td>${row.file_name}</td><td>${row.status}</td>`;
    tr.onclick = () => showDetail(row.row_index);
    tb.appendChild(tr);
  });
}

let detailRow = null;
async function showDetail(rowIndex) {
  detailRow = rowIndex;
  const r = await api(`/api/extract/detail/${rowIndex}`);
  const tb = document.querySelector("#detail-table tbody");
  tb.innerHTML = "";
  r.detail.forEach((d) => {
    const tr = document.createElement("tr");
    tr.className = "conf-" + d.confidence;
    tr.innerHTML = `<td>${d.field}</td>
      <td><input type="text" value="${d.value}" data-field="${d.field}"></td>
      <td>${d.confidence}</td>`;
    const input = tr.querySelector("input");
    input.onchange = () => api("/api/extract/update", { method: "POST", body: JSON.stringify({
      row_index: rowIndex, field_name: d.field, value: input.value,
    })});
    tb.appendChild(tr);
  });
}

async function startExtract() {
  try {
    const r = await api("/api/extract/start", { method: "POST" });
    pollJob(r.job_id, "extract-progress", refreshExtractTable);
  } catch (e) { toast(e.message); }
}

async function exportExcel() {
  try {
    const res = await fetch("/api/extract/export", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: "" }),
    });
    if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "output.xlsx"; a.click();
    URL.revokeObjectURL(url);
    toast("已导出");
  } catch (e) { toast(e.message); }
}

// ---- job polling ----
function pollJob(jobId, progressEl, onDone) {
  const el = document.getElementById(progressEl);
  const timer = setInterval(async () => {
    try {
      const j = await api(`/api/job/${jobId}`);
      el.textContent = `${j.current}/${j.total}`;
      if (j.done) {
        clearInterval(timer);
        el.textContent += j.error ? ` 出错: ${j.error}` : " 完成";
        onDone();
      }
    } catch (e) { clearInterval(timer); }
  }, 1000);
}

// ---- init ----
renderStepper();
refreshState();
