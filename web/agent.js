const agentIds = (id) => document.getElementById(id);
let agentToken = null;
let agentReady = {gemini_ready: false, smtp_ready: false};

function agentMessage(message) {
  agentIds("agent-status").textContent = message;
}

function agentToggleWeekday() {
  agentIds("agent-weekday-row").hidden = agentIds("agent-frequency").value !== "weekly";
}

function agentPayload() {
  return {
    area: agentIds("agent-area").value.trim(),
    frequency: agentIds("agent-frequency").value,
    email: agentIds("agent-email").value.trim(),
    hour: agentIds("agent-hour").value,
    weekday: Number(agentIds("agent-weekday").value),
  };
}

async function agentRequest(route, payload) {
  const response = await fetch(`/api/agent/${route}`, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload), cache: "no-store",
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Falha no servidor local.");
  return body;
}

async function agentStatus() {
  try {
    const response = await fetch("/api/agent/status", {cache: "no-store"});
    if (!response.ok) throw new Error();
    const data = await response.json();
    agentReady = data.capabilities;
    const item = data.subscription;
    if (item) {
      agentIds("agent-area").value = item.area;
      agentIds("agent-frequency").value = item.frequency;
      agentIds("agent-email").value = item.email;
      agentIds("agent-hour").value = item.hour;
      agentIds("agent-weekday").value = String(item.weekday);
      agentToggleWeekday();
    }
    const subscription = item?.active ? `Agendamento ${item.frequency === "daily" ? "diário" : "semanal"} ativo.` : "Nenhum envio automático ativo.";
    agentMessage(`${subscription} ${!agentReady.gemini_ready || !agentReady.smtp_ready ? "A prévia ou o envio podem estar indisponíveis nesta instalação." : "Gere uma prévia para conferir o relatório antes do envio."}${data.last_error ? ` ${data.last_error}` : ""}`);
    agentIds("agent-disable-button").disabled = !item?.active;
  } catch {
    agentMessage("Esta função usa o servidor local do projeto. Execute python web_server.py para gerar relatórios e agendar envios.");
    agentIds("agent-preview-button").disabled = true;
    agentIds("agent-save-button").disabled = true;
    agentIds("agent-disable-button").disabled = true;
  }
}

function agentShowSources(articles) {
  const host = agentIds("agent-sources");
  host.replaceChildren();
  if (!articles.length) return;
  const heading = document.createElement("h4");
  heading.textContent = "Notícias selecionadas";
  host.append(heading);
  for (const article of articles) {
    const entry = document.createElement("article");
    const link = document.createElement("a");
    link.href = article.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = article.title;
    const detail = document.createElement("span");
    detail.textContent = `${new Intl.DateTimeFormat("pt-BR").format(new Date(`${article.date}T12:00:00`))} · ${article.category}`;
    entry.append(link, detail);
    host.append(entry);
  }
}

async function agentPreview() {
  const payload = agentPayload();
  if (!payload.area || payload.area.length < 2) {
    agentMessage("Informe uma área ou assunto com pelo menos duas letras.");
    agentIds("agent-area").focus();
    return;
  }
  const button = agentIds("agent-preview-button");
  button.disabled = true;
  agentToken = null;
  agentIds("agent-send-button").hidden = true;
  agentMessage("Selecionando notícias e preparando a prévia...");
  try {
    const result = await agentRequest("preview", payload);
    agentIds("agent-period").textContent = `Período: ${result.start} a ${result.end}. Acervo até ${result.snapshot}.`;
    if (result.report_html) {
      agentIds("agent-report").innerHTML = result.report_html;
      agentShowSources([]);
    } else {
      agentIds("agent-report").textContent = result.notice || "";
      agentShowSources(result.articles);
    }
    agentToken = result.token;
    agentIds("agent-send-button").hidden = !(agentToken && agentReady.smtp_ready);
    agentMessage(result.notice || "Relatório gerado. Confira os destaques e as fontes antes de enviar.");
  } catch (error) {
    agentMessage(error.message);
  } finally {
    button.disabled = false;
  }
}

async function agentSave(event) {
  event.preventDefault();
  if (!agentIds("agent-form").reportValidity()) return;
  const button = agentIds("agent-save-button");
  button.disabled = true;
  try {
    await agentRequest("save", agentPayload());
    await agentStatus();
    agentMessage(`${agentIds("agent-status").textContent} O envio ocorrerá no horário escolhido se houver notícias novas e o acervo estiver atualizado.`);
  } catch (error) {
    agentMessage(error.message);
  } finally {
    button.disabled = false;
  }
}

async function agentSend() {
  if (!agentToken) return;
  const email = agentIds("agent-email");
  if (!email.reportValidity()) return;
  const button = agentIds("agent-send-button");
  button.disabled = true;
  agentMessage("Enviando a prévia por e-mail...");
  try {
    await agentRequest("send", {token: agentToken, email: email.value.trim()});
    agentToken = null;
    button.hidden = true;
    agentMessage("Prévia enviada. Confira a caixa de entrada e a pasta de spam.");
  } catch (error) {
    agentMessage(error.message);
  } finally {
    button.disabled = false;
  }
}

agentIds("agent-frequency").addEventListener("change", () => {agentToggleWeekday(); agentToken = null; agentIds("agent-send-button").hidden = true;});
agentIds("agent-area").addEventListener("input", () => {agentToken = null; agentIds("agent-send-button").hidden = true;});
agentIds("agent-preview-button").addEventListener("click", agentPreview);
agentIds("agent-form").addEventListener("submit", agentSave);
agentIds("agent-send-button").addEventListener("click", agentSend);
agentIds("agent-disable-button").addEventListener("click", async () => {
  try {
    await agentRequest("disable", {});
    await agentStatus();
  } catch (error) {
    agentMessage(error.message);
  }
});
agentToggleWeekday();
agentStatus();
