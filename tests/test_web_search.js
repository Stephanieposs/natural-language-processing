const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const load = (name) => JSON.parse(fs.readFileSync(path.join(root, "web", "data", name), "utf8"));
const source = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");
const core = source.slice(0, source.indexOf('$("search-form").addEventListener'));
const context = vm.createContext({console});
vm.runInContext(core, context);
const catalog = load("catalog.json");
const lexical = load("tfidf.json");
const semantic = load("word2vec.json");
context.catalog = catalog;
context.lexical = lexical;
context.semantic = semantic;
vm.runInContext(`state.catalog = catalog;
  state.lexical = new Map(lexical.map(([term, idf, postings]) => [term, [idf, postings]]));
  state.semantic = semantic;
  state.stopwords = new Set(catalog.stopwords);`, context);

function results(query, method) {
  context.query = query;
  context.method = method;
  return vm.runInContext(`(() => {
    const queryTerms = tokens(query);
    const tfidf = rank(lexicalScores(queryTerms), "");
    const word2vec = rank(semanticScores(queryTerms).scores, "");
    const ranked = method === "tfidf" ? tfidf : method === "word2vec" ? word2vec : hybridRank(tfidf, word2vec);
    return ranked.slice(0, 5).map((item) => item.document.title);
  })()`, context);
}

assert.equal(catalog.documents.length, catalog.published_documents);
assert.ok(catalog.documents.length > 1000);
assert.equal(semantic.document_vectors.length, catalog.documents.length);
assert.ok(results("acidente no centro", "tfidf").some((title) => /acidente|colisão|ferid/i.test(title)));
assert.ok(results("acidente no centro", "word2vec").some((title) => /acidente|colisão|ferid/i.test(title)));
assert.ok(results("oktoberfest", "tfidf").some((title) => /Oktoberfest/i.test(title)));
assert.equal(results("acidente no centro", "hybrid").length, 5);
assert.equal(results("xyztermoausente", "hybrid").length, 0);
const shared = vm.runInContext(`(() => {
  const terms = tokens("itoupava");
  const lexical = rank(lexicalScores(terms), "");
  const semantic = rank(semanticScores(terms).scores, "");
  const item = hybridRank(lexical, semantic).find((result) => result.tfidf && result.word2vec);
  return {score: item.score, tfidf: item.tfidf, word2vec: item.word2vec};
})()`, context);
assert.ok(shared.tfidf.score > 0 && shared.word2vec.score > 0);
assert.ok(Math.abs(shared.score - (
  1 / (60 + shared.tfidf.position) + 1 / (60 + shared.word2vec.position)
)) < 1e-9);
console.log("Busca TF-IDF, Word2Vec e hibrida: OK");
