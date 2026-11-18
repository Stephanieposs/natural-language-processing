const state = {catalog: null, lexical: null, semantic: null, stopwords: null, query: "", recentItems: [], recentVisible: 20};
const $ = (id) => document.getElementById(id);
const formatDate = (value) => new Intl.DateTimeFormat("pt-BR").format(new Date(`${value}T12:00:00`));

function tokens(text) {
  return text.toLocaleLowerCase("pt-BR").split(/[^\p{L}]+/u)
    .filter((term) => term && !state.stopwords.has(term));
}

function lexicalScores(queryTerms) {
  const counts = new Map();
  for (const term of queryTerms) counts.set(term, (counts.get(term) || 0) + 1);
  const weighted = [];
  for (const [term, count] of counts) {
    const entry = state.lexical.get(term);
    if (entry) weighted.push([entry, count * entry[0]]);
  }
  const norm = Math.hypot(...weighted.map((item) => item[1]));
  const scores = new Float32Array(state.catalog.documents.length);
  if (!norm) return scores;
  for (const [[, postings], weight] of weighted) {
    for (const [index, value] of postings) scores[index] += (weight / norm) * value;
  }
  return scores;
}

function semanticScores(queryTerms) {
  const {dimension, word_vectors: vocabulary, document_vectors: documents} = state.semantic;
  const query = new Float32Array(dimension);
  let found = 0;
  for (const term of queryTerms) {
    const vector = vocabulary[term];
    if (!vector) continue;
    found++;
    for (let i = 0; i < dimension; i++) query[i] += vector[i];
  }
  const scores = new Float32Array(documents.length);
  if (!found) return {scores, found};
  const norm = Math.hypot(...query);
  if (!norm) return {scores, found};
  for (let i = 0; i < dimension; i++) query[i] /= norm;
  for (let doc = 0; doc < documents.length; doc++) {
    let score = 0;
    for (let i = 0; i < dimension; i++) score += query[i] * documents[doc][i];
    scores[doc] = score;
  }
  return {scores, found};
}

function rank(scores, category) {
  return state.catalog.documents.map((document, index) => ({document, index, score: scores[index]}))
    .filter((item) => item.score > 0 && (!category || item.document.category === category))
    .sort((a, b) => b.score - a.score || a.index - b.index);
}

function hybridRank(lexical, semantic) {
  const combined = new Map();
  const positions = [new Map(), new Map()];
  for (const [methodIndex, list] of [lexical, semantic].entries()) {
    list.slice(0, 100).forEach((item, position) => {
      const value = combined.get(item.index) || 0;
      combined.set(item.index, value + 1 / (60 + position + 1));
      positions[methodIndex].set(item.index, {score: item.score, position: position + 1});
    });
  }
  return [...combined.entries()].map(([index, score]) => ({
    index, score, document: state.catalog.documents[index],
    tfidf: positions[0].get(index) || null,
    word2vec: positions[1].get(index) || null,
  })).sort((a, b) => b.score - a.score || a.index - b.index);
}

function node(name, className, content) {
  const element = document.createElement(name);
  if (className) element.className = className;
  if (content !== undefined) element.textContent = content;
  return element;
}

function renderRecent() {
  const category = $("recent-category").value;
  const items = state.recentItems.filter((item) => !category || item.category === category);
  const host = $("recent-list");
  host.replaceChildren();
  for (const item of items.slice(0, state.recentVisible)) {
    const entry = node("article", "recent-item");
    const link = node("a", "", item.title);
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    entry.append(link, node("span", "", `${formatDate(item.date)} · ${item.category}`));
    host.append(entry);
  }
  $("recent-more").hidden = items.length <= state.recentVisible;
}

function appendResult(parent, item, position, method) {
  const article = node("article", "result");
  if (method === "hybrid") article.classList.add("result-hybrid");
  article.append(node("span", "result-rank", String(position)));
  const body = node("div");
  const heading = node("h3");
  const link = node("a", "", item.document.title);
  link.href = item.document.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  heading.append(link);
  const meta = node("div", "result-meta");
  meta.append(node("span", "result-category", item.document.category));
  meta.append(node("span", "", formatDate(item.document.date)));
  meta.append(node("span", "", "Blog do Jaime"));
  body.append(heading, meta);
  if (method === "hybrid") {
    const breakdown = node("div", "score-breakdown");
    for (const [name, component] of [["TF-IDF", item.tfidf], ["Word2Vec", item.word2vec]]) {
      breakdown.append(node(
        "span", "", component
          ? `${name}: ${component.score.toFixed(3)} de similaridade · ${component.position}ª posição`
          : `${name}: fora dos 100 primeiros`,
      ));
    }
    body.append(breakdown);
  }
  article.append(body);
  const score = node("div", "result-score", item.score.toFixed(method === "hybrid" ? 4 : 3));
  score.append(node("span", "", method === "hybrid" ? "pontuação híbrida (RRF)" : `similaridade ${method === "tfidf" ? "TF-IDF" : "Word2Vec"}`));
  article.append(score);
  parent.append(article);
}

function showEmpty(title, detail) {
  const message = node("div", "empty");
  message.append(node("strong", "", title), node("span", "", detail));
  $("results").replaceChildren(message);
}

function showComparison(lexical, semantic, limit) {
  const wrapper = node("div", "comparison-grid");
  for (const [title, results, method] of [
    ["TF-IDF", lexical, "tfidf"], ["Word2Vec", semantic, "word2vec"],
  ]) {
    const column = node("div", "comparison-column");
    column.append(node("h3", "", title));
    if (!results.length) column.append(node("p", "", "Sem resultados para esta consulta."));
    results.slice(0, limit).forEach((item, index) => appendResult(column, item, index + 1, method));
    wrapper.append(column);
  }
  const note = node("p", "comparison-note", "TF-IDF compara palavras em vetores esparsos; Word2Vec compara médias de vetores densos. Por isso, Word2Vec pode mostrar um número maior para a mesma notícia sem ser necessariamente mais relevante. Compare a ordem e os títulos, não os valores entre colunas.");
  $("results").replaceChildren(note, wrapper);
  $("result-status").textContent = "Rankings lado a lado";
}

function search() {
  const query = $("query").value.trim();
  state.query = query;
  if (!query || !state.catalog) return;
  const queryTerms = tokens(query);
  const category = $("category").value;
  const limit = Number($("limit").value);
  const method = document.querySelector('input[name="method"]:checked').value;
  $("results-title").textContent = `“${query}”`;
  if (!queryTerms.length) {
    showEmpty("Consulta sem termos úteis", "Tente acrescentar palavras sobre o assunto desejado.");
    $("result-status").textContent = "0 resultados";
    return;
  }
  const lexical = rank(lexicalScores(queryTerms), category);
  const semantic = rank(semanticScores(queryTerms).scores, category);
  if (method === "compare") {
    showComparison(lexical, semantic, limit);
    return;
  }
  const list = method === "tfidf" ? lexical : method === "word2vec" ? semantic : hybridRank(lexical, semantic);
  const results = node("div", "result-list");
  list.slice(0, limit).forEach((item, index) => appendResult(results, item, index + 1, method));
  if (results.children.length) $("results").replaceChildren(results);
  else showEmpty("Nenhuma notícia encontrada", "Tente outra expressão ou escolha Todas em Categoria.");
  $("result-status").textContent = `${list.length} correspondências`;
}

async function initialize() {
  try {
    const files = ["catalog.json", "tfidf.json", "word2vec.json"];
    const responses = await Promise.all(files.map((file) => fetch(`data/${file}`)));
    for (const response of responses) if (!response.ok) throw new Error(`Falha ao carregar ${response.url}`);
    const [catalog, lexical, semantic] = await Promise.all(responses.map((response) => response.json()));
    if (semantic.document_vectors.length !== catalog.documents.length) throw new Error("Índices incompatíveis.");
    state.catalog = catalog;
    state.lexical = new Map(lexical.map(([term, idf, postings]) => [term, [idf, postings]]));
    state.semantic = semantic;
    state.stopwords = new Set(catalog.stopwords);
    $("document-count").textContent = catalog.published_documents.toLocaleString("pt-BR");
    $("snapshot-range").textContent = `Recorte: ${formatDate(catalog.oldest_date)} a ${formatDate(catalog.snapshot_date)}`;
    $("result-status").textContent = "Pronto para buscar";
    const categories = [...new Set(catalog.documents.map((item) => item.category))].sort((a, b) => a.localeCompare(b, "pt-BR"));
    for (const category of categories) {
      const option = node("option", "", category);
      option.value = category;
      $("category").append(option);
      const recentOption = node("option", "", category);
      recentOption.value = category;
      $("recent-category").append(recentOption);
    }
    state.recentItems = [...catalog.documents].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
    renderRecent();
    $("query").value = "acidente no centro";
    search();
  } catch (error) {
    console.error(error);
    $("result-status").textContent = "Erro ao carregar índice";
    showEmpty("Não foi possível abrir a busca", "Use um servidor local ou verifique os arquivos de dados da página.");
  }
}

$("search-form").addEventListener("submit", (event) => {event.preventDefault(); search();});
for (const button of document.querySelectorAll("[data-query]")) {
  button.addEventListener("click", () => {$("query").value = button.dataset.query; search();});
}
const methodInfo = {
  hybrid: {
    title: "Híbrida: combina duas buscas",
    text: "Combina TF-IDF e Word2Vec pelo índice RRF (fusão recíproca de rankings): soma 1/(60 + posição) de cada lista. Uma notícia em 1º lugar nas duas recebe 2/61 ≈ 0,0328. O índice ordena resultados; não é uma porcentagem nem uma similaridade.",
    example: "Use quando quiser reunir correspondência de palavras e semelhança de assunto.",
  },
  tfidf: {
    title: "TF-IDF: procura as palavras digitadas",
    text: "Prioriza notícias que contêm os termos da consulta e dá mais peso aos menos comuns. Funciona bem para nomes, lugares e eventos; pode deixar de fora textos que usam outras palavras.",
    example: "Exemplo: “Oktoberfest” tende a destacar títulos e textos que mencionam o evento.",
  },
  word2vec: {
    title: "Word2Vec: aproxima assuntos parecidos",
    text: "Compara representações das palavras aprendidas com as notícias. Pode encontrar textos do mesmo tema sem repetir exatamente a consulta, mas pode perder detalhes como o local citado.",
    example: "Exemplo: uma busca sobre chuva pode trazer outras notícias ligadas ao tempo.",
  },
  compare: {
    title: "Comparar: veja as duas listas lado a lado",
    text: "Mostra TF-IDF à esquerda e Word2Vec à direita para a mesma consulta. Compare os títulos e a ordem; as similaridades dos dois métodos usam escalas diferentes.",
    example: "Use para observar quando a busca por palavras e a busca por assunto concordam ou divergem.",
  },
};
function updateMethodExplanation() {
  const method = document.querySelector('input[name="method"]:checked').value;
  const info = methodInfo[method];
  $("method-help-title").textContent = info.title;
  $("method-help-text").textContent = info.text;
  $("method-help-example").textContent = info.example;
}
for (const input of document.querySelectorAll('input[name="method"], #category, #limit')) {
  input.addEventListener("change", () => {
    if (input.name === "method") updateMethodExplanation();
    if (state.query) search();
  });
}
$("recent-category").addEventListener("change", () => {state.recentVisible = 20; renderRecent();});
$("recent-more").addEventListener("click", () => {state.recentVisible += 20; renderRecent();});

const tabs = [...document.querySelectorAll('[role="tab"]')];
function activateTab(tab, focus = false) {
  for (const item of tabs) {
    const selected = item === tab;
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
    $(item.getAttribute("aria-controls")).hidden = !selected;
  }
  if (window.location.hash !== `#${tab.getAttribute("aria-controls")}`) {
    history.replaceState(null, "", `#${tab.getAttribute("aria-controls")}`);
  }
  if (focus) tab.focus();
}
for (const tab of tabs) {
  tab.addEventListener("click", () => activateTab(tab));
  tab.addEventListener("keydown", (event) => {
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      activateTab(tabs[event.key === "Home" ? 0 : tabs.length - 1], true);
      return;
    }
    const offset = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!offset) return;
    event.preventDefault();
    activateTab(tabs[(tabs.indexOf(tab) + offset + tabs.length) % tabs.length], true);
  });
}
const initialTab = tabs.find((tab) => `#${tab.getAttribute("aria-controls")}` === window.location.hash);
if (initialTab) activateTab(initialTab);
window.addEventListener("hashchange", () => {
  const tab = tabs.find((item) => `#${item.getAttribute("aria-controls")}` === window.location.hash);
  if (tab) activateTab(tab);
});
initialize();
