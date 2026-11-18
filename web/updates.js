const alertStorageKey = "blumenau-em-texto-alertas-v1";
let alertCatalog = [];
let alertRules = [];
const newAlertCounts = new Map();
let localServerAvailable = false;

function saveAlertRules() {
  localStorage.setItem(alertStorageKey, JSON.stringify(alertRules));
}

function matchingNews(term) {
  const needle = term.toLocaleLowerCase("pt-BR");
  return alertCatalog.filter((item) =>
    `${item.title} ${item.category}`.toLocaleLowerCase("pt-BR").includes(needle)
  ).sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
}

function renderAlerts() {
  const host = document.getElementById("alert-list");
  host.replaceChildren();
  if (!alertRules.length) {
    const message = document.createElement("p");
    message.textContent = "Nenhum assunto cadastrado. Adicione uma palavra ou expressão para acompanhar títulos e categorias do acervo.";
    host.append(message);
    return;
  }
  for (const rule of alertRules) {
    const matches = matchingNews(rule.term);
    const item = document.createElement("div");
    item.className = "alert-item";
    const head = document.createElement("div");
    head.className = "alert-item-head";
    const label = document.createElement("strong");
    label.textContent = rule.term;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remover";
    remove.addEventListener("click", () => {
      alertRules = alertRules.filter((entry) => entry !== rule);
      saveAlertRules();
      renderAlerts();
    });
    head.append(label, remove);
    const summary = document.createElement("p");
    const newCount = newAlertCounts.get(rule.term.toLocaleLowerCase("pt-BR")) || 0;
    summary.textContent = `${matches.length} correspondência(s) no índice${newCount ? ` · ${newCount} nova(s) desde a última visita` : ""}.`;
    item.append(head, summary);
    for (const news of matches.slice(0, 3)) {
      const link = document.createElement("a");
      link.href = news.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = `${news.title} · ${news.date.split("-").reverse().join("/")}`;
      item.append(link);
    }
    host.append(item);
  }
}

async function loadAlerts() {
  try {
    const response = await fetch("data/catalog.json");
    if (!response.ok) throw new Error("Acervo indisponível");
    const catalog = await response.json();
    alertCatalog = catalog.documents;
    const previousDay = new Date(`${catalog.snapshot_date}T12:00:00`);
    previousDay.setDate(previousDay.getDate() - 1);
    document.getElementById("update-since").value = previousDay.toISOString().slice(0, 10);
    document.getElementById("update-target").value = String(Math.min(catalog.published_documents + 500, 10000));
    const saved = JSON.parse(localStorage.getItem(alertStorageKey) || "[]");
    alertRules = Array.isArray(saved) ? saved.filter((item) => typeof item.term === "string" && Array.isArray(item.seen)) : [];
    for (const rule of alertRules) {
      const matches = matchingNews(rule.term);
      const seen = new Set(rule.seen);
      newAlertCounts.set(rule.term.toLocaleLowerCase("pt-BR"), matches.filter((item) => !seen.has(item.url)).length);
      rule.seen = matches.map((item) => item.url);
    }
    saveAlertRules();
    renderAlerts();
  } catch (error) {
    console.error(error);
    document.getElementById("alert-list").textContent = "Não foi possível consultar os alertas neste navegador.";
  }
}

document.getElementById("alert-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("alert-keyword");
  const term = input.value.trim();
  if (!term || alertRules.some((rule) => rule.term.toLocaleLowerCase("pt-BR") === term.toLocaleLowerCase("pt-BR"))) return;
  alertRules.push({term, seen: matchingNews(term).map((item) => item.url)});
  saveAlertRules();
  input.value = "";
  renderAlerts();
});

document.getElementById("update-mode").addEventListener("change", (event) => {
  document.getElementById("update-since-field").hidden = event.target.value !== "since";
  document.getElementById("update-target-field").hidden = event.target.value !== "target";
});

async function postLocal(route, payload) {
  const response = await fetch(route, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Falha no servidor local.");
  return data;
}

async function updateStatus() {
  const status = document.getElementById("update-status");
  const scheduleStatus = document.getElementById("schedule-status");
  try {
    const response = await fetch("api/status", {cache: "no-store"});
    if (!response.ok) throw new Error("Servidor de atualização ausente");
    const data = await response.json();
    localServerAvailable = true;
    document.getElementById("update-submit").disabled = data.running;
    document.getElementById("reload-data").hidden = data.exit_code !== 0;
    document.getElementById("schedule-enable").disabled = false;
    document.getElementById("schedule-disable").disabled = !data.schedule_active;
    if (data.schedule_time) document.getElementById("schedule-time").value = data.schedule_time;
    scheduleStatus.textContent = data.schedule_active
      ? `Rotina diária ativa neste computador${data.schedule_time ? ` às ${data.schedule_time}` : ""}.`
      : "Rotina diária desativada.";
    status.textContent = data.running
      ? `Processando: ${data.lines.at(-1) || "aguarde"}`
      : data.exit_code === 0
        ? "Atualização concluída. Recarregue a página para consultar os novos dados."
        : data.exit_code !== null
          ? `Atualização interrompida: ${data.lines.at(-1) || "verifique o terminal"}`
          : "Servidor local pronto para atualizar o acervo.";
  } catch {
    localServerAvailable = false;
    document.getElementById("update-submit").disabled = true;
    document.getElementById("reload-data").hidden = true;
    document.getElementById("schedule-enable").disabled = true;
    document.getElementById("schedule-disable").disabled = true;
    status.textContent = "Atualização local indisponível nesta hospedagem. Execute python web_server.py no projeto para ativar os controles.";
    scheduleStatus.textContent = "Agendamento disponível somente com o servidor local aberto.";
  }
}

document.getElementById("update-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!localServerAvailable) return;
  const mode = document.getElementById("update-mode").value;
  const payload = mode === "since"
    ? {mode, since: document.getElementById("update-since").value}
    : {mode, target: Number(document.getElementById("update-target").value)};
  try {
    await postLocal("api/update", payload);
    await updateStatus();
  } catch (error) {
    document.getElementById("update-status").textContent = error.message;
  }
});

document.getElementById("schedule-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await postLocal("api/schedule", {active: true, time: document.getElementById("schedule-time").value});
    await updateStatus();
  } catch (error) {
    document.getElementById("schedule-status").textContent = error.message;
  }
});
document.getElementById("schedule-disable").addEventListener("click", async () => {
  try {
    await postLocal("api/schedule", {active: false});
    await updateStatus();
  } catch (error) {
    document.getElementById("schedule-status").textContent = error.message;
  }
});
document.getElementById("reload-data").addEventListener("click", () => window.location.reload());

loadAlerts();
updateStatus();
setInterval(() => {if (localServerAvailable) updateStatus();}, 5000);
