"use strict";
// Веб-форма: ввод (форма или JSON) → POST /api/generate → карточка с кнопками «копировать».
// Весь пользовательский текст выводится через textContent — без innerHTML.

const $ = (sel) => document.querySelector(sel);
const form = $("#form");
const jsonBox = $("#json");
let mode = "form";
let current = null; // последний результат {card, missing, warnings, markdown, …}
let view = "card";

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}

// ---------- ввод ----------

function specRow(name = "", value = "") {
  const row = el("div", { class: "spec" },
    el("input", { placeholder: "характеристика", "aria-label": "Характеристика", maxlength: "100" }),
    el("input", { placeholder: "значение", "aria-label": "Значение", maxlength: "500" }),
    el("button", { type: "button", class: "link", title: "Удалить", "aria-label": "Удалить", onclick: () => row.remove() }, "×"));
  row.children[0].value = name;
  row.children[1].value = value;
  $("#specs").append(row);
}

function readForm() {
  const specs = {};
  for (const row of document.querySelectorAll("#specs .spec")) {
    const [k, v] = [row.children[0].value.trim(), row.children[1].value.trim()];
    if (k) specs[k] = v;
  }
  return {
    name: form.name.value.trim(),
    manufacturer: form.manufacturer.value.trim(),
    specs,
    description: form.description.value.trim(),
  };
}

function fillForm(p) {
  form.name.value = p.name || "";
  form.manufacturer.value = p.manufacturer || "";
  form.description.value = p.description || "";
  $("#specs").replaceChildren();
  const specs = p.specs && typeof p.specs === "object" ? Object.entries(p.specs) : [];
  specs.forEach(([k, v]) => specRow(k, v == null ? "" : String(v)));
  if (!specs.length) specRow();
  jsonBox.value = JSON.stringify(p, null, 2);
}

function setMode(next) {
  if (next === mode) return;
  if (next === "json") {
    jsonBox.value = JSON.stringify(readForm(), null, 2);
  } else {
    try { fillForm(JSON.parse(jsonBox.value)); } catch { return showError("В JSON ошибка — исправьте, прежде чем переключиться на форму."); }
  }
  mode = next;
  form.hidden = mode !== "form";
  jsonBox.hidden = mode !== "json";
  document.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-selected", b.dataset.mode === mode));
  hideError();
}

// ---------- запрос ----------

function showError(message, details = []) {
  const box = $("#error");
  box.replaceChildren(el("strong", {}, message), details.length ? el("ul", {}, details.map((d) => el("li", {}, d))) : "");
  box.hidden = false;
}
function hideError() { $("#error").hidden = true; }

async function generate() {
  hideError();
  const body = mode === "json" ? jsonBox.value : JSON.stringify(readForm());
  if (mode === "form" && !form.name.value.trim()) return showError("Укажите название товара.");
  const button = $("#generate");
  const started = Date.now();
  button.disabled = true;
  const tick = setInterval(() => {
    $("#progress").textContent = `Модель пишет карточку… ${Math.round((Date.now() - started) / 1000)} с (обычно 30–90 с)`;
  }, 500);
  try {
    const resp = await fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body });
    const data = await resp.json().catch(() => ({ error: `Сервер ответил ${resp.status}` }));
    if (!resp.ok) return showError(data.error || `Ошибка ${resp.status}`, data.details || []);
    showResult(data, `Сгенерировано за ${Math.round((Date.now() - started) / 1000)} с`);
  } catch {
    showError("Сервис недоступен. Проверьте соединение и повторите.");
  } finally {
    clearInterval(tick);
    $("#progress").textContent = "";
    button.disabled = false;
  }
}

// ---------- результат ----------

async function copy(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    const old = button.textContent;
    button.textContent = "Скопировано";
    setTimeout(() => (button.textContent = old), 1200);
  } catch { /* нет доступа к буферу — текст всё равно можно выделить */ }
}

function block(title, text, content) {
  return el("div", { class: "block" },
    el("div", { class: "row between" }, el("h3", {}, title),
      el("button", { type: "button", class: "copy", onclick: (e) => copy(text, e.target) }, "Копировать")),
    content);
}

function list(items) { return el("ul", {}, items.map((i) => el("li", {}, i))); }

function renderCard(card) {
  const specsText = card.specs.map((s) => `${s.name}: ${s.value}`).join("\n");
  const table = el("table", {},
    el("thead", {}, el("tr", {}, el("th", {}, "Характеристика"), el("th", {}, "Значение"))),
    el("tbody", {}, card.specs.map((s) =>
      el("tr", { class: s.source === "missing" ? "missing" : "" }, el("td", {}, s.name), el("td", {}, s.value)))));
  const c = card.commercial;
  const commercialText = `Кому подходит:\n- ${c.audience.join("\n- ")}\n\nКакие задачи решает:\n- ${c.tasks.join("\n- ")}`;
  const desc = el("div", { class: "text" }, card.seo_description.split("\n\n").map((p) => el("p", {}, p)));
  $("#view-card").replaceChildren(
    block(`SEO-заголовок · ${card.seo_title.length} / 70`, card.seo_title, el("p", { class: "title" }, card.seo_title)),
    block(`SEO-описание · ${card.seo_description.length} симв. (800–1200)`, card.seo_description, desc),
    block("Характеристики", specsText, card.specs.length ? table : el("p", { class: "muted" }, "данных нет")),
    block("Поисковые запросы", card.search_queries.join("\n"), list(card.search_queries)),
    block("Для менеджера", commercialText,
      el("div", {}, el("h4", {}, "Кому подходит"), list(c.audience), el("h4", {}, "Какие задачи решает"), list(c.tasks))));
}

function setView(next) {
  view = next;
  document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-selected", b.dataset.view === view));
  $("#view-card").hidden = view !== "card";
  $("#view-raw").hidden = view === "card";
  if (current && view !== "card") $("#raw").textContent = rawText();
}

function rawText() {
  if (view === "markdown") return current.markdown;
  const { markdown, ...rest } = current;
  return JSON.stringify(rest, null, 2);
}

function alertBox(sel, title, items) {
  const box = $(sel);
  box.hidden = !items.length;
  box.replaceChildren(el("strong", {}, title), list(items));
}

function showResult(result, meta) {
  current = result;
  $("#result").hidden = false;
  $("#meta").textContent = `${meta} · модель ${result.model} · попыток: ${result.attempts}`;
  alertBox("#warnings", "Проверить вручную (не прошло автоматическую проверку):", result.warnings);
  alertBox("#missing", "Нужно уточнить:", result.missing);
  renderCard(result.card);
  setView(view);
  if (window.matchMedia("(max-width: 960px)").matches) $("#result").scrollIntoView({ behavior: "smooth" });
}

// ---------- старт ----------

async function loadExamples() {
  try {
    const examples = await (await fetch("/api/examples")).json();
    for (const ex of examples) {
      $("#examples").append(el("button", {
        type: "button", class: "chip", title: "Загрузить пример и показать сохранённый результат",
        onclick: () => {
          fillForm(ex.input);
          if (mode === "json") jsonBox.value = JSON.stringify(ex.input, null, 2);
          showResult(ex.result, "Сохранённый результат");
        },
      }, ex.input.name));
    }
  } catch { /* без примеров форма работает */ }
}

async function checkLlm() {
  const badge = $("#llm");
  try {
    const h = await (await fetch("/api/health")).json();
    const up = h.llm === "up";
    badge.textContent = up ? `модель ${h.model}: онлайн` : "модель офлайн — доступны сохранённые примеры";
    badge.className = `status ${up ? "up" : "down"}`;
  } catch {
    badge.textContent = "сервис недоступен";
    badge.className = "status down";
  }
}

document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
$("[data-copy-raw]").addEventListener("click", (e) => current && copy(rawText(), e.target));
$("#add-spec").addEventListener("click", () => specRow());
$("#generate").addEventListener("click", generate);
specRow();
loadExamples();
checkLlm();
