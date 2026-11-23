const resultColors = ["#12635b", "#b74c37", "#536f9e", "#9a6231", "#72508d", "#5d7a37", "#aa5e83", "#2d8196", "#9e8d36", "#656b76", "#ba7862", "#36845c"];
const svgNamespace = "http://www.w3.org/2000/svg";
let modelResults;

function renderClusterChart(method) {
  const chart = document.getElementById("cluster-chart");
  const {points, clusters, pca_variance: variance} = modelResults[method];
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const width = Math.max(maxX - minX, 0.000001);
  const height = Math.max(maxY - minY, 0.000001);
  const xAxis = document.createElementNS(svgNamespace, "line");
  xAxis.setAttribute("x1", "30"); xAxis.setAttribute("y1", "410");
  xAxis.setAttribute("x2", "870"); xAxis.setAttribute("y2", "410");
  xAxis.setAttribute("stroke", "#9eaeae");
  const yAxis = document.createElementNS(svgNamespace, "line");
  yAxis.setAttribute("x1", "30"); yAxis.setAttribute("y1", "20");
  yAxis.setAttribute("x2", "30"); yAxis.setAttribute("y2", "410");
  yAxis.setAttribute("stroke", "#9eaeae");
  const xLabel = document.createElementNS(svgNamespace, "text");
  xLabel.setAttribute("x", "450"); xLabel.setAttribute("y", "435");
  xLabel.setAttribute("text-anchor", "middle");
  xLabel.setAttribute("fill", "#52616a");
  xLabel.textContent = "PCA 1";
  const yLabel = document.createElementNS(svgNamespace, "text");
  yLabel.setAttribute("x", "10"); yLabel.setAttribute("y", "215");
  yLabel.setAttribute("transform", "rotate(-90 10 215)");
  yLabel.setAttribute("text-anchor", "middle");
  yLabel.setAttribute("fill", "#52616a");
  yLabel.textContent = "PCA 2";
  const elements = points.map(([x, y, cluster, title]) => {
    const circle = document.createElementNS(svgNamespace, "circle");
    circle.setAttribute("cx", String(30 + 840 * (x - minX) / width));
    circle.setAttribute("cy", String(20 + 390 * (1 - (y - minY) / height)));
    circle.setAttribute("r", "3");
    circle.setAttribute("fill", resultColors[cluster % resultColors.length]);
    circle.setAttribute("fill-opacity", "0.6");
    const tooltip = document.createElementNS(svgNamespace, "title");
    tooltip.textContent = `${title} · grupo ${cluster + 1}`;
    circle.append(tooltip);
    return circle;
  });
  chart.replaceChildren(xAxis, yAxis, xLabel, yLabel, ...elements);
  const legend = document.getElementById("cluster-legend");
  legend.replaceChildren();
  for (let group = 0; group < clusters; group++) {
    const item = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.style.background = resultColors[group % resultColors.length];
    item.append(swatch, `Grupo ${group + 1}`);
    legend.append(item);
  }
  chart.setAttribute("aria-label", `Projeção PCA de ${points.length} notícias em ${clusters} grupos por ${method === "tfidf" ? "TF-IDF" : "Word2Vec"}`);
  const projection = `PCA 1 e PCA 2 explicam ${((variance[0] + variance[1]) * 100).toFixed(1).replace(".", ",")}% da variação dos vetores.`;
  const detail = method === "word2vec_public_10"
    ? `Reagrupamento das ${points.length.toLocaleString("pt-BR")} notícias públicas: silhouette ${modelResults[method].silhouette.toFixed(3).replace(".", ",")}, pureza ${modelResults[method].purity.toFixed(3).replace(".", ",")} e menor grupo com ${modelResults[method].minimum_cluster_size} notícias.`
    : "Grupos treinados na base válida completa; as categorias excluídas do site podem deixar grupos pequenos neste recorte.";
  document.getElementById("cluster-caption").textContent =
    `${clusters} grupos · ${projection} ${detail} Passe o cursor sobre um ponto para ver o título.`;
}

function renderCategoryChart() {
  const host = document.getElementById("category-chart");
  const max = modelResults.category_counts[0][1];
  for (const [category, count] of modelResults.category_counts) {
    const row = document.createElement("div");
    row.className = "category-row";
    const label = document.createElement("span");
    label.textContent = category;
    const track = document.createElement("div");
    track.className = "category-track";
    const bar = document.createElement("div");
    bar.className = "category-bar";
    bar.style.width = `${100 * count / max}%`;
    track.append(bar);
    const value = document.createElement("strong");
    value.textContent = count.toLocaleString("pt-BR");
    row.append(label, track, value);
    host.append(row);
  }
}

async function loadModelResults() {
  try {
    const response = await fetch("data/results.json");
    if (!response.ok) throw new Error("Resultados indisponíveis");
    modelResults = await response.json();
    document.getElementById("metric-public").textContent = modelResults.published_documents.toLocaleString("pt-BR");
    document.getElementById("metric-tfidf").textContent = modelResults.tfidf.silhouette.toFixed(3).replace(".", ",");
    document.getElementById("metric-word2vec").textContent = modelResults.word2vec.silhouette.toFixed(3).replace(".", ",");
    document.getElementById("current-purity").textContent =
      `Pureza por categoria: TF-IDF ${modelResults.tfidf.purity.toFixed(3).replace(".", ",")} e Word2Vec ${modelResults.word2vec.purity.toFixed(3).replace(".", ",")}. É a proporção de notícias da categoria predominante em cada grupo, ponderada pelo tamanho dos grupos; categorias editoriais amplas limitam sua interpretação.`;
    document.getElementById("model-results-intro").textContent =
      `Métricas originais calculadas com ${modelResults.source_documents.toLocaleString("pt-BR")} notícias válidas até ${new Intl.DateTimeFormat("pt-BR").format(new Date(`${modelResults.snapshot_date}T12:00:00`))}. A busca pública contém ${modelResults.published_documents.toLocaleString("pt-BR")} delas; a opção Word2Vec com 10 grupos foi treinada somente nesse recorte.`;
    renderClusterChart(document.getElementById("cluster-method").value);
    renderCategoryChart();
  } catch (error) {
    console.error(error);
    document.getElementById("model-results-intro").textContent = "Não foi possível carregar os resultados atualizados.";
  }
}

document.getElementById("cluster-method").addEventListener("change", (event) => {
  if (modelResults) renderClusterChart(event.target.value);
});
loadModelResults();
