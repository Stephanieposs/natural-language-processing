"""Publica metricas e pontos PCA da base atual para a aba Resultados."""

import json
from collections import Counter
from pathlib import Path

import pandas as pd

from representacao_textual import calcular_hash_base


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
OUTPUT = ROOT / "web" / "data" / "results.json"


def export():
    catalog = json.loads((ROOT / "web/data/catalog.json").read_text(encoding="utf-8"))
    source = pd.read_json(PROCESSED / "noticias_nlp.jsonl", lines=True)
    tfidf = pd.read_json(PROCESSED / "noticias_clusters.jsonl", lines=True)
    word2vec = pd.read_json(PROCESSED / "noticias_clusters_word2vec_k12.jsonl", lines=True)
    summary = json.loads((REPORTS / "summary.json").read_text(encoding="utf-8"))
    w2v_meta = json.loads(
        (REPORTS / "cluster_visualization_word2vec_k12.json").read_text(encoding="utf-8")
    )
    w2v_groups = pd.read_csv(REPORTS / "cluster_summary_word2vec_k12.csv")
    if not len(source) == len(tfidf) == len(word2vec):
        raise RuntimeError("Os agrupamentos nao correspondem ao mesmo acervo.")
    expected_hash = calcular_hash_base(source)
    if w2v_meta["dataset_hash"] != expected_hash:
        raise RuntimeError("Agrupamento Word2Vec desatualizado.")
    for frame in (tfidf, word2vec):
        if frame["content_hash"].tolist() != source["content_hash"].tolist():
            raise RuntimeError("Ordem dos agrupamentos nao corresponde ao acervo.")
    selected = [item["id"] for item in catalog["documents"]]
    if not selected or catalog["source_documents"] != len(source) or max(selected) >= len(source):
        raise RuntimeError("Catalogo web nao corresponde ao acervo.")
    if any(
        catalog["documents"][position]["url"] != source.iloc[index]["url"]
        for position, index in enumerate(selected)
    ):
        raise RuntimeError("Catalogo web nao corresponde a ordem do acervo.")

    def points(frame):
        return [
            [round(float(row["cluster_x"]), 5), round(float(row["cluster_y"]), 5),
             int(row["cluster"]), catalog["documents"][position]["title"]]
            for position, (_, row) in enumerate(frame.iloc[selected].iterrows())
        ]

    counts = Counter(item["category"] for item in catalog["documents"])
    data = {
        "snapshot_date": catalog["snapshot_date"],
        "source_documents": len(source),
        "published_documents": len(selected),
        "category_counts": counts.most_common(),
        "tfidf": {
            "clusters": int(summary["vectorization"]["selected_clusters"]),
            "silhouette": summary["vectorization"]["silhouette"],
            "purity": summary["vectorization"]["category_evaluation"]["cluster_category_purity"],
            "pca_variance": summary["vectorization"]["pca_explained_variance"][:2],
            "points": points(tfidf),
        },
        "word2vec": {
            "clusters": int(w2v_meta["selected_clusters"]),
            "silhouette": w2v_meta["silhouette"],
            "purity": round(
                float(w2v_groups["quantidade_categoria_majoritaria"].sum()
                      / w2v_groups["quantidade_noticias"].sum()), 6
            ),
            "pca_variance": w2v_meta["pca_explained_variance"][:2],
            "points": points(word2vec),
        },
    }
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Resultados atuais exportados: {len(selected)} noticias publicas.")


if __name__ == "__main__":
    export()
