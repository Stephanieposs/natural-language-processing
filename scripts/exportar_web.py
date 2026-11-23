"""Exporta um indice estatico e revisavel para a demonstracao web.

Execute depois de --agrupar e --indexar-busca --sem-bert. O texto integral
das noticias nao faz parte do pacote publicado.
"""

import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from gensim.models import Word2Vec
from nltk.corpus import stopwords

from representacao_textual import calcular_hash_base, carregar_embeddings_csv


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUTPUT = ROOT / "web" / "data"
EXCLUDED_CATEGORIES = {"Aniversários", "Falecidos"}
EXCLUDED_TITLE_PREFIXES = ("falecidos nas ",)
MAX_WORD_VECTORS = 5000


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def compact_vector(vector, digits):
    return [round(float(value), digits) for value in vector]


def export():
    source = pd.read_json(PROCESSED / "noticias_nlp.jsonl", lines=True)
    manifest = json.loads((PROCESSED / "indice_busca.json").read_text(encoding="utf-8"))
    dataset_hash = calcular_hash_base(source)
    for kind in ("lexical", "semantic"):
        section = manifest.get(kind, {})
        if section.get("dataset_hash") != dataset_hash or section.get("documents") != len(source):
            raise RuntimeError(f"Indice {kind} desatualizado. Regenere-o antes da exportacao.")

    categories = source["category"].fillna("").str.split(",").str[0].str.strip()
    excluded_by_title = source["title"].fillna("").str.strip().str.casefold().str.startswith(EXCLUDED_TITLE_PREFIXES)
    selected = np.flatnonzero((~categories.isin(EXCLUDED_CATEGORIES) & ~excluded_by_title).to_numpy())
    documents = []
    for original_id in selected:
        row = source.iloc[int(original_id)]
        documents.append({
            "id": int(original_id),
            "title": str(row["title"]),
            "date": str(row["published_at"])[:10],
            "category": categories.iloc[int(original_id)],
            "url": str(row["url"]),
        })

    vectorizer = joblib.load(PROCESSED / "vectorizer_tfidf.joblib")
    matrix = pd.read_csv(PROCESSED / "tfidf_matrix.csv").drop(columns="id").to_numpy(dtype=np.float32)
    if matrix.shape != (len(source), len(vectorizer.get_feature_names_out())):
        raise RuntimeError("Matriz TF-IDF incompatível com o vetorizador.")
    matrix = matrix[selected]
    terms = []
    for column, term in enumerate(vectorizer.get_feature_names_out()):
        nonzero = np.flatnonzero(matrix[:, column])
        if len(nonzero):
            terms.append([
                str(term),
                round(float(vectorizer.idf_[column]), 6),
                [[int(i), round(float(matrix[i, column]), 6)] for i in nonzero],
            ])

    model = Word2Vec.load(str(PROCESSED / "modelo_word2vec.model"))
    embeddings = carregar_embeddings_csv(PROCESSED / "embeddings_word2vec.csv")
    if embeddings.shape != (len(source), model.vector_size):
        raise RuntimeError("Embeddings Word2Vec incompatíveis com a base.")
    counts = Counter(
        token for original_id in selected
        for token in source.iloc[int(original_id)]["tokens_sem_stopwords"]
    )
    vocabulary = [
        term for term, _ in counts.most_common() if term in model.wv
    ][:MAX_WORD_VECTORS]
    word_vectors = {term: compact_vector(model.wv[term], 4) for term in vocabulary}
    document_vectors = embeddings[selected]
    norms = np.linalg.norm(document_vectors, axis=1, keepdims=True)
    document_vectors = document_vectors / np.maximum(norms, 1e-9)

    dates = [item["date"] for item in documents if item["date"]]
    save_json(OUTPUT / "catalog.json", {
        "source": "Blog do Jaime",
        "source_url": "https://blogdojaime.com.br/",
        "snapshot_date": max(dates),
        "oldest_date": min(dates),
        "source_documents": len(source),
        "published_documents": len(documents),
        "excluded_categories": sorted(EXCLUDED_CATEGORIES),
        "documents": documents,
        "stopwords": sorted(stopwords.words("portuguese")),
    })
    save_json(OUTPUT / "tfidf.json", terms)
    save_json(OUTPUT / "word2vec.json", {
        "dimension": model.vector_size,
        "document_vectors": [compact_vector(vector, 5) for vector in document_vectors],
        "word_vectors": word_vectors,
        "vocabulary_size": len(vocabulary),
    })
    print(f"Exportadas {len(documents)} noticias de {len(source)}; ate {max(dates)}.")


if __name__ == "__main__":
    export()
