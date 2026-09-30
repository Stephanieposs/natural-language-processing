"""Busca com Bag of Words, TF-IDF, Word2Vec ou BERTimbau."""

import re
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from bert import gerar_indice_bert, pontuar_bert
from metricas_busca import calcular_relevancia
from representacao_textual import (
    calcular_hash_base,
    carregar_manifest_indices,
    carregar_matriz_csv,
    salvar_manifest_indices,
)
from word2vec import gerar_indice_word2vec, pontuar_word2vec


PROJECT_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_DIR / "data/processed"
NLP_PATH = PROCESSED_DIR / "noticias_nlp.jsonl"
CLUSTERS_PATH = PROCESSED_DIR / "noticias_clusters.jsonl"
TFIDF_MATRIX_PATH = PROCESSED_DIR / "tfidf_matrix.csv"
TFIDF_VECTORIZER_PATH = PROCESSED_DIR / "vectorizer_tfidf.joblib"
BOW_MATRIX_PATH = PROCESSED_DIR / "bow_matrix.csv"
BOW_VECTORIZER_PATH = PROCESSED_DIR / "vectorizer_bow.joblib"
SEARCH_FIELDS = (
    "document_id",
    "title",
    "published_at",
    "category",
    "url",
    "content_hash",
    "cluster",
    "cluster_label",
)


def _documentos_busca(dataframe):
    documents = pd.DataFrame(index=dataframe.index)
    documents["document_id"] = np.arange(len(dataframe), dtype=int)
    for field in SEARCH_FIELDS[1:]:
        documents[field] = dataframe[field] if field in dataframe else ""
    return documents


def _carregar_base_com_clusters():
    if not NLP_PATH.exists():
        raise FileNotFoundError(
            f"Base de PLN nao encontrada em {NLP_PATH}. Execute primeiro o pipeline."
        )
    dataframe = pd.read_json(NLP_PATH, lines=True)
    if CLUSTERS_PATH.exists():
        clustered = pd.read_json(CLUSTERS_PATH, lines=True)
        if (
            len(clustered) == len(dataframe)
            and calcular_hash_base(clustered) == calcular_hash_base(dataframe)
        ):
            for field in ("cluster", "cluster_label"):
                if field in clustered:
                    dataframe[field] = clustered[field]
    return dataframe


def indexar_busca(incluir_bert=True):
    print("Lendo a base preparada para PLN...", flush=True)
    dataframe = _carregar_base_com_clusters()
    dataset_hash = calcular_hash_base(dataframe)
    previous_manifest = carregar_manifest_indices()
    previous_semantic = previous_manifest.get("semantic", {})

    same_dataset = previous_semantic.get("dataset_hash") == dataset_hash
    word2vec_metadata = gerar_indice_word2vec(
        dataframe, reutilizar=same_dataset
    )

    if incluir_bert:
        bert_metadata = gerar_indice_bert(
            dataframe,
            reutilizar=same_dataset,
            metadados_anteriores=previous_semantic.get("bert"),
        )
    else:
        bert_metadata = {"enabled": False, "model": None, "dimension": None}

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = previous_manifest
    manifest["semantic"] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "documents": len(dataframe),
        "dataset_hash": dataset_hash,
        "word2vec": word2vec_metadata,
        "bert": bert_metadata,
    }
    salvar_manifest_indices(manifest)
    print(f"Indice concluido para {len(dataframe)} noticias.", flush=True)
    return manifest


def _preparar_consulta(query):
    from nltk.corpus import stopwords

    tokens = re.findall(r"[^\W\d_]+", query.casefold(), flags=re.UNICODE)
    stopwords_pt = set(stopwords.words("portuguese"))
    return [token for token in tokens if token not in stopwords_pt]


def _validar_indice_lexico(documents):
    manifesto = carregar_manifest_indices().get("lexical", {})
    if not manifesto:
        raise FileNotFoundError(
            "Indices lexicos nao encontrados. Execute: python projeto_pln.py --agrupar"
        )
    if manifesto.get("documents") != len(documents):
        raise RuntimeError(
            "Os indices lexicos nao correspondem a base atual. Execute --agrupar."
        )
    if manifesto.get("dataset_hash") != calcular_hash_base(documents):
        raise RuntimeError(
            "Os documentos mudaram desde a vetorizacao. Execute --agrupar."
        )
    return manifesto


def _validar_indice_semantico(documents):
    manifesto = carregar_manifest_indices().get("semantic", {})
    if not manifesto:
        raise FileNotFoundError(
            "Indice semantico nao encontrado. Execute: python projeto_pln.py --indexar-busca"
        )
    if manifesto.get("documents") != len(documents):
        raise RuntimeError(
            "O indice semantico nao corresponde a base atual. Execute --indexar-busca."
        )
    if manifesto.get("dataset_hash") != calcular_hash_base(documents):
        raise RuntimeError(
            "Os documentos mudaram desde a indexacao. Execute --indexar-busca."
        )
    return manifesto


def _carregar_documentos():
    source = CLUSTERS_PATH if CLUSTERS_PATH.exists() else NLP_PATH
    if not source.exists():
        raise FileNotFoundError(
            "Base processada ausente. Execute primeiro o pipeline de PLN."
        )
    return _documentos_busca(pd.read_json(source, lines=True))


def _pontuar_representacao_lexica(
    query_tokens,
    total_documents,
    metrica,
    matrix_path,
    vectorizer_path,
    nome,
):
    if not matrix_path.exists() or not vectorizer_path.exists():
        raise FileNotFoundError(
            f"Indice {nome} ausente. Execute primeiro: python projeto_pln.py --agrupar"
        )
    vectorizer = joblib.load(vectorizer_path)
    matrix = carregar_matriz_csv(matrix_path)
    if matrix.shape[0] != total_documents:
        raise RuntimeError(f"A matriz {nome} esta desatualizada. Execute --agrupar.")
    query_vector = vectorizer.transform([query_tokens])
    return calcular_relevancia(query_vector, matrix, metrica)


def _pontuar_bow(query_tokens, total_documents, metrica="cosseno"):
    return _pontuar_representacao_lexica(
        query_tokens,
        total_documents,
        metrica,
        BOW_MATRIX_PATH,
        BOW_VECTORIZER_PATH,
        "Bag of Words",
    )


def _pontuar_tfidf(query_tokens, total_documents, metrica="cosseno"):
    return _pontuar_representacao_lexica(
        query_tokens,
        total_documents,
        metrica,
        TFIDF_MATRIX_PATH,
        TFIDF_VECTORIZER_PATH,
        "TF-IDF",
    )


def buscar(query, metodo="tfidf", top_k=10, metrica="cosseno"):
    query = query.strip()
    if not query:
        raise ValueError("A consulta nao pode estar vazia.")
    if top_k < 1:
        raise ValueError("top-k deve ser maior que zero.")

    documents = _carregar_documentos()
    if metodo in ("bow", "tfidf"):
        _validar_indice_lexico(documents)
        manifest = {}
    else:
        manifest = _validar_indice_semantico(documents)
    tokens = _preparar_consulta(query)
    if metodo == "bow":
        scores = _pontuar_bow(tokens, len(documents), metrica)
    elif metodo == "tfidf":
        scores = _pontuar_tfidf(tokens, len(documents), metrica)
    elif metodo == "word2vec":
        scores = pontuar_word2vec(tokens, len(documents), metrica)
    elif metodo == "bert":
        if not manifest.get("bert", {}).get("enabled"):
            raise FileNotFoundError(
                "Indice BERT ausente. Execute --indexar-busca sem --sem-bert."
            )
        scores = pontuar_bert(query, len(documents), metrica)
    else:
        raise ValueError("Metodo deve ser bow, tfidf, word2vec ou bert.")

    limit = min(top_k, len(documents))
    indices = np.argsort(scores)[::-1][:limit]
    result = documents.iloc[indices].copy()
    result.insert(0, "posicao", np.arange(1, limit + 1))
    result.insert(1, "score", np.asarray(scores)[indices])
    result.insert(2, "metodo", metodo)
    result.insert(3, "metrica", metrica)
    result.insert(4, "consulta", query)
    return result


def imprimir_resultados(result):
    print(f"\n{len(result)} noticias encontradas:\n")
    for row in result.itertuples(index=False):
        date = str(row.published_at)[:10] if pd.notna(row.published_at) else ""
        print(f"{row.posicao}. [{row.score:.4f}] {row.title}")
        print(f"   {date} | {row.category} | cluster {row.cluster}")
        print(f"   {row.url}\n")
