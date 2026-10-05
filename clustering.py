"""Agrupamento das noticias com TF-IDF e K-Means."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity

from bag_of_words import gerar_bag_of_words
from representacao_textual import (
    calcular_hash_base,
    carregar_base_nlp,
    carregar_manifest_indices,
    construir_corpus,
    salvar_manifest_indices,
)
from tf_idf import gerar_tfidf
from visualizacao_clusters import (
    CLUSTER_3D_HTML_PATH,
    CLUSTER_HTML_PATH,
    gerar_html_clusters,
)


# Quantidade de classes principais observadas nas categorias do Blog do Jaime.
NUMERO_CLUSTERS = 9
TOP_TERMOS = 8
RANDOM_STATE = 42

PROJECT_DIR = Path(__file__).resolve().parent
PROCESSED_PATH = PROJECT_DIR / "data/processed"
REPORTS_PATH = PROJECT_DIR / "reports"
CLUSTER_MODEL_PATH = PROCESSED_PATH / "modelo_kmeans.joblib"
CLUSTERS_JSONL_PATH = PROCESSED_PATH / "noticias_clusters.jsonl"
CLUSTER_SUMMARY_PATH = REPORTS_PATH / "cluster_summary.csv"
CLUSTER_CATEGORY_MATRIX_PATH = REPORTS_PATH / "cluster_category_matrix.csv"
CLUSTER_CATEGORY_MAPPING_PATH = REPORTS_PATH / "cluster_category_mapping.csv"
CLUSTER_CONFUSION_MATRIX_PATH = REPORTS_PATH / "cluster_confusion_matrix.csv"
CENTROID_DISTANCES_PATH = REPORTS_PATH / "cluster_centroid_distances.csv"
SIMILARITY_BOW_PATH = PROCESSED_PATH / "similaridade_bow.csv"
SIMILARITY_TFIDF_PATH = PROCESSED_PATH / "similaridade_tfidf.csv"
SUMMARY_PATH = REPORTS_PATH / "summary.json"


def treinar_kmeans(matriz_tfidf):
    modelo = KMeans(
        n_clusters=NUMERO_CLUSTERS,
        random_state=RANDOM_STATE,
        n_init=10,
    )
    clusters = modelo.fit_predict(matriz_tfidf)
    return modelo, clusters


def reduzir_para_tres_dimensoes(matriz_tfidf):
    pca = PCA(n_components=3, random_state=RANDOM_STATE)
    coordenadas = pca.fit_transform(matriz_tfidf.toarray())
    return coordenadas, pca.explained_variance_ratio_


def calcular_coesao_cluster(matriz_tfidf, indices):
    if len(indices) < 2:
        return 1.0
    similaridades = cosine_similarity(matriz_tfidf[indices])
    return float(similaridades[np.triu_indices(len(indices), k=1)].mean())


def resumir_clusters(modelo, vetorizador, matriz_tfidf, dataframe):
    termos = vetorizador.get_feature_names_out()
    resumos = []
    nomes = {}

    for cluster_id in range(NUMERO_CLUSTERS):
        indices = np.where(modelo.labels_ == cluster_id)[0]
        ordem = modelo.cluster_centers_[cluster_id].argsort()[::-1][:TOP_TERMOS]
        termos_principais = termos[ordem].tolist()
        nome = " / ".join(termos_principais[:3])
        nomes[cluster_id] = nome

        resumos.append(
            {
                "cluster": cluster_id,
                "rotulo": nome,
                "quantidade_noticias": len(indices),
                "coesao_media_cosseno": round(
                    calcular_coesao_cluster(matriz_tfidf, indices), 6
                ),
                "termos_principais": ", ".join(termos_principais),
            }
        )

    dataframe["cluster_label"] = dataframe["cluster"].map(nomes)
    return resumos


def normalizar_categoria(categorias):
    return (
        categorias.fillna("Sem categoria")
        .astype(str)
        .str.split(",")
        .str[0]
        .str.strip()
        .replace("", "Sem categoria")
    )


def avaliar_clusters_por_categoria(dataframe, resumos):
    dataframe["categoria_real"] = normalizar_categoria(dataframe["category"])

    matriz_categoria_cluster = pd.crosstab(
        dataframe["categoria_real"],
        dataframe["cluster"],
    )
    categorias_ordenadas = (
        dataframe["categoria_real"].value_counts().sort_values(ascending=False).index
    )
    matriz_categoria_cluster = matriz_categoria_cluster.reindex(
        index=categorias_ordenadas,
        columns=range(NUMERO_CLUSTERS),
        fill_value=0,
    )

    mapeamento = {}
    linhas_mapeamento = []
    resumos_por_cluster = {resumo["cluster"]: resumo for resumo in resumos}

    for cluster_id in range(NUMERO_CLUSTERS):
        contagens = matriz_categoria_cluster[cluster_id]
        categoria = contagens.idxmax()
        quantidade = int(contagens.loc[categoria])
        total_cluster = int(contagens.sum())
        pureza = quantidade / total_cluster if total_cluster else 0.0
        mapeamento[cluster_id] = categoria

        resumo = resumos_por_cluster[cluster_id]
        resumo["categoria_majoritaria"] = categoria
        resumo["quantidade_categoria_majoritaria"] = quantidade
        resumo["pureza_categoria"] = round(pureza, 6)

        linhas_mapeamento.append(
            {
                "cluster": cluster_id,
                "cluster_label": resumo["rotulo"],
                "categoria_atribuida": categoria,
                "quantidade_noticias": total_cluster,
                "quantidade_categoria_atribuida": quantidade,
                "pureza_categoria": round(pureza, 6),
                "termos_principais": resumo["termos_principais"],
            }
        )

    dataframe["cluster_category"] = dataframe["cluster"].map(mapeamento)
    matriz_confusao = pd.crosstab(
        dataframe["categoria_real"],
        dataframe["cluster_category"],
    ).reindex(index=categorias_ordenadas, fill_value=0)

    matriz_confusao = matriz_confusao.reindex(
        columns=categorias_ordenadas,
        fill_value=0,
    )
    acertos = sum(
        matriz_confusao.loc[categoria, categoria]
        for categoria in matriz_confusao.index
        if categoria in matriz_confusao.columns
    )

    metricas = {
        "cluster_category_accuracy": round(float(acertos / len(dataframe)), 6),
        "cluster_category_purity": round(
            float(
                sum(
                    linha["quantidade_categoria_atribuida"]
                    for linha in linhas_mapeamento
                )
                / len(dataframe)
            ),
            6,
        ),
        "cluster_category_matrix": CLUSTER_CATEGORY_MATRIX_PATH.name,
        "cluster_category_mapping": CLUSTER_CATEGORY_MAPPING_PATH.name,
        "cluster_confusion_matrix": CLUSTER_CONFUSION_MATRIX_PATH.name,
    }
    return (
        matriz_categoria_cluster,
        pd.DataFrame(linhas_mapeamento),
        matriz_confusao,
        metricas,
    )


def calcular_distancias_centroides(modelo):
    similaridades = cosine_similarity(modelo.cluster_centers_)
    distancias = np.clip(1 - similaridades, 0, 2)
    rotulos = [f"cluster_{indice}" for indice in range(NUMERO_CLUSTERS)]
    return pd.DataFrame(distancias, index=rotulos, columns=rotulos)


def salvar_matrizes_similaridade(matriz_bow, matriz_tfidf):
    identificadores = range(matriz_bow.shape[0])
    for matriz, caminho in (
        (matriz_bow, SIMILARITY_BOW_PATH),
        (matriz_tfidf, SIMILARITY_TFIDF_PATH),
    ):
        similaridades = cosine_similarity(matriz)
        dataframe = pd.DataFrame(
            similaridades,
            index=identificadores,
            columns=identificadores,
        )
        dataframe.index.name = "id"
        dataframe.to_csv(caminho, float_format="%.6f", encoding="utf-8-sig")


def salvar_resultados(
    dataframe,
    modelo,
    resumos,
    distancias_centroides,
    matriz_categoria_cluster,
    mapeamento_categorias,
    matriz_confusao,
):
    PROCESSED_PATH.mkdir(parents=True, exist_ok=True)
    REPORTS_PATH.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, CLUSTER_MODEL_PATH)
    dataframe.to_json(
        CLUSTERS_JSONL_PATH,
        orient="records",
        lines=True,
        force_ascii=False,
        date_format="iso",
    )
    pd.DataFrame(resumos).to_csv(CLUSTER_SUMMARY_PATH, index=False, encoding="utf-8")
    matriz_categoria_cluster.to_csv(CLUSTER_CATEGORY_MATRIX_PATH, encoding="utf-8")
    mapeamento_categorias.to_csv(
        CLUSTER_CATEGORY_MAPPING_PATH,
        index=False,
        encoding="utf-8",
    )
    matriz_confusao.to_csv(CLUSTER_CONFUSION_MATRIX_PATH, encoding="utf-8")
    distancias_centroides.to_csv(CENTROID_DISTANCES_PATH, float_format="%.6f")


def atualizar_resumo_geral(resumo_vetorizacao):
    resumo = {}
    if SUMMARY_PATH.exists():
        resumo = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    resumo["vectorization"] = resumo_vetorizacao
    SUMMARY_PATH.write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def registrar_indices_lexicos(dataframe):
    """Registra a base usada por Bag of Words e TF-IDF."""
    manifesto = carregar_manifest_indices()
    manifesto["lexical"] = {
        "dataset_hash": calcular_hash_base(dataframe),
        "documents": len(dataframe),
        "representations": ("bow", "tfidf"),
    }
    salvar_manifest_indices(manifesto)


def gerar_vetores_e_clusters(dataframe, verbose=True):
    dataframe = dataframe.reset_index(drop=True).copy()
    corpus = construir_corpus(dataframe)

    if verbose:
        print("Gerando Bag of Words...", flush=True)
    _, matriz_bow = gerar_bag_of_words(corpus)

    if verbose:
        print("Gerando TF-IDF...", flush=True)
    vetorizador_tfidf, matriz_tfidf = gerar_tfidf(corpus)

    if verbose:
        print(f"Agrupando em {NUMERO_CLUSTERS} clusters...", flush=True)
    modelo, clusters = treinar_kmeans(matriz_tfidf)
    dataframe["cluster"] = clusters

    if verbose:
        print("Calculando similaridades e analise dos clusters...", flush=True)
    salvar_matrizes_similaridade(matriz_bow, matriz_tfidf)
    coordenadas, variancia = reduzir_para_tres_dimensoes(matriz_tfidf)
    dataframe["cluster_x"] = coordenadas[:, 0]
    dataframe["cluster_y"] = coordenadas[:, 1]
    dataframe["cluster_z"] = coordenadas[:, 2]
    resumos = resumir_clusters(
        modelo, vetorizador_tfidf, matriz_tfidf, dataframe
    )
    (
        matriz_categoria_cluster,
        mapeamento_categorias,
        matriz_confusao,
        metricas_categorias,
    ) = avaliar_clusters_por_categoria(dataframe, resumos)
    distancias_centroides = calcular_distancias_centroides(modelo)

    salvar_resultados(
        dataframe,
        modelo,
        resumos,
        distancias_centroides,
        matriz_categoria_cluster,
        mapeamento_categorias,
        matriz_confusao,
    )
    registrar_indices_lexicos(dataframe)
    gerar_html_clusters(dataframe, variancia)

    resumo = {
        "documents": len(dataframe),
        "bow_features": int(matriz_bow.shape[1]),
        "tfidf_features": int(matriz_tfidf.shape[1]),
        "selected_clusters": NUMERO_CLUSTERS,
        "silhouette": round(
            float(silhouette_score(matriz_tfidf, clusters, metric="cosine")), 6
        ),
        "pca_explained_variance": [round(float(valor), 6) for valor in variancia],
        "document_similarity": {
            "bow": SIMILARITY_BOW_PATH.name,
            "tfidf": SIMILARITY_TFIDF_PATH.name,
        },
        "centroid_distances": CENTROID_DISTANCES_PATH.name,
        "category_evaluation": metricas_categorias,
        "vectorizer": {
            "source": "tokens_sem_stopwords",
            "min_df": 2,
            "max_features": 15_000,
        },
    }
    atualizar_resumo_geral(resumo)
    return dataframe, resumo


def agrupar_base_existente():
    dataframe = carregar_base_nlp()
    resultado, resumo = gerar_vetores_e_clusters(dataframe)
    print(
        f"Agrupamento concluido: {len(resultado)} noticias em "
        f"{resumo['selected_clusters']} clusters."
    )
    print(f"Visualizacao 2D: {CLUSTER_HTML_PATH}")
    print(f"Visualizacao 3D: {CLUSTER_3D_HTML_PATH}")


if __name__ == "__main__":
    agrupar_base_existente()
