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

from bag_of_words import BOW_MATRIX_PATH, gerar_bag_of_words
from bert import BERT_EMBEDDINGS_PATH
from representacao_textual import (
    calcular_hash_base,
    carregar_base_nlp,
    carregar_embeddings_csv,
    carregar_manifest_indices,
    carregar_matriz_csv,
    construir_corpus,
    salvar_manifest_indices,
)
from tf_idf import TFIDF_MATRIX_PATH, gerar_tfidf
from visualizacao_clusters import (
    CLUSTER_3D_HTML_PATH,
    CLUSTER_HTML_PATH,
    gerar_html_clusters,
    gerar_html_clusters_generico,
)
from word2vec import WORD2VEC_EMBEDDINGS_PATH


# Quantidade de clusters usada para comparar com as categorias do Blog do Jaime.
NUMERO_CLUSTERS = 12
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
CLUSTER_REPRESENTATION_COMPARISON_PATH = (
    REPORTS_PATH / "cluster_representations_comparison.csv"
)
WORD2VEC_CLUSTERS_JSONL_PATH = PROCESSED_PATH / "noticias_clusters_word2vec_k12.jsonl"
WORD2VEC_CLUSTER_SUMMARY_PATH = REPORTS_PATH / "cluster_summary_word2vec_k12.csv"
WORD2VEC_CLUSTER_HTML_PATH = REPORTS_PATH / "clusters_word2vec_k12.html"
WORD2VEC_CLUSTER_3D_HTML_PATH = REPORTS_PATH / "clusters_word2vec_k12_3d.html"
K_CANDIDATOS_COMPARACAO = (9, 12, 13)


def treinar_kmeans(matriz_tfidf):
    return treinar_kmeans_com_k(matriz_tfidf, NUMERO_CLUSTERS)


def treinar_kmeans_com_k(matriz, numero_clusters):
    modelo = KMeans(
        n_clusters=numero_clusters,
        random_state=RANDOM_STATE,
        n_init=10,
    )
    clusters = modelo.fit_predict(matriz)
    return modelo, clusters


def reduzir_para_tres_dimensoes(matriz_tfidf):
    pca = PCA(n_components=3, random_state=RANDOM_STATE)
    coordenadas = pca.fit_transform(matriz_tfidf.toarray())
    return coordenadas, pca.explained_variance_ratio_


def reduzir_array_para_tres_dimensoes(matriz):
    pca = PCA(n_components=3, random_state=RANDOM_STATE)
    coordenadas = pca.fit_transform(matriz)
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


def calcular_pureza_categoria(dataframe, clusters, numero_clusters):
    dados = pd.DataFrame(
        {
            "categoria_real": normalizar_categoria(dataframe["category"]),
            "cluster": clusters,
        }
    )
    matriz = pd.crosstab(dados["categoria_real"], dados["cluster"]).reindex(
        columns=range(numero_clusters),
        fill_value=0,
    )
    categorias_majoritarias = []
    acertos = 0
    for cluster_id in range(numero_clusters):
        contagens = matriz[cluster_id]
        if contagens.sum() == 0:
            continue
        categoria = contagens.idxmax()
        categorias_majoritarias.append(categoria)
        acertos += int(contagens.loc[categoria])
    return {
        "pureza_categoria": round(float(acertos / len(dados)), 6),
        "categorias_majoritarias": ", ".join(sorted(set(categorias_majoritarias))),
        "quantidade_categorias_majoritarias": len(set(categorias_majoritarias)),
    }


def calcular_distancias_centroides(modelo):
    similaridades = cosine_similarity(modelo.cluster_centers_)
    distancias = np.clip(1 - similaridades, 0, 2)
    rotulos = [f"cluster_{indice}" for indice in range(NUMERO_CLUSTERS)]
    return pd.DataFrame(distancias, index=rotulos, columns=rotulos)


def resumir_distancias_centroides(modelo):
    similaridades = cosine_similarity(modelo.cluster_centers_)
    distancias = np.clip(1 - similaridades, 0, 2)
    valores = distancias[np.triu_indices(distancias.shape[0], k=1)]
    return {
        "distancia_media_centroides": round(float(valores.mean()), 6),
        "distancia_minima_centroides": round(float(valores.min()), 6),
    }


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


def carregar_representacoes_para_comparacao(total_documentos):
    representacoes = {
        "bow": (BOW_MATRIX_PATH, carregar_matriz_csv),
        "tfidf": (TFIDF_MATRIX_PATH, carregar_matriz_csv),
        "word2vec": (WORD2VEC_EMBEDDINGS_PATH, carregar_embeddings_csv),
        "bert": (BERT_EMBEDDINGS_PATH, carregar_embeddings_csv),
    }
    matrizes = {}
    for nome, (caminho, carregador) in representacoes.items():
        if not caminho.exists():
            continue
        matriz = carregador(caminho)
        if matriz.shape[0] == total_documentos:
            matrizes[nome] = matriz
    return matrizes


def comparar_representacoes_clusters(
    dataframe=None,
    k_candidatos=K_CANDIDATOS_COMPARACAO,
):
    dataframe = carregar_base_nlp() if dataframe is None else dataframe.copy()
    dataframe = dataframe.reset_index(drop=True)
    matrizes = carregar_representacoes_para_comparacao(len(dataframe))
    if not matrizes:
        raise FileNotFoundError(
            "Nenhuma representacao vetorial encontrada. Execute --agrupar e "
            "--indexar-busca antes da comparacao."
        )

    linhas = []
    for representacao, matriz in matrizes.items():
        for numero_clusters in k_candidatos:
            modelo, clusters = treinar_kmeans_com_k(matriz, numero_clusters)
            pureza = calcular_pureza_categoria(dataframe, clusters, numero_clusters)
            distancias = resumir_distancias_centroides(modelo)
            linhas.append(
                {
                    "representacao": representacao,
                    "clusters": numero_clusters,
                    "documentos": int(matriz.shape[0]),
                    "dimensoes": int(matriz.shape[1]),
                    "silhouette_cosseno": round(
                        float(silhouette_score(matriz, clusters, metric="cosine")),
                        6,
                    ),
                    **pureza,
                    **distancias,
                }
            )

    resultado = pd.DataFrame(linhas).sort_values(
        ["silhouette_cosseno", "pureza_categoria"],
        ascending=False,
    )
    REPORTS_PATH.mkdir(parents=True, exist_ok=True)
    resultado.to_csv(
        CLUSTER_REPRESENTATION_COMPARISON_PATH,
        index=False,
        encoding="utf-8",
    )
    return resultado


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


def comparar_clusters_existentes():
    resultado = comparar_representacoes_clusters()
    print("Comparacao de clusterizacao por representacao:")
    print(resultado.to_string(index=False))
    print(f"\nRelatorio: {CLUSTER_REPRESENTATION_COMPARISON_PATH}")


def gerar_visualizacao_word2vec_k12(dataframe=None):
    dataframe = carregar_base_nlp() if dataframe is None else dataframe.copy()
    dataframe = dataframe.reset_index(drop=True)
    if not WORD2VEC_EMBEDDINGS_PATH.exists():
        raise FileNotFoundError(
            "Embeddings Word2Vec ausentes. Execute: python projeto_pln.py --indexar-busca --sem-bert"
        )

    embeddings = carregar_embeddings_csv(WORD2VEC_EMBEDDINGS_PATH)
    if embeddings.shape[0] != len(dataframe):
        raise RuntimeError("Os embeddings Word2Vec nao correspondem a base atual.")

    modelo, clusters = treinar_kmeans_com_k(embeddings, 12)
    dataframe["cluster"] = clusters
    dataframe["categoria_real"] = normalizar_categoria(dataframe["category"])

    matriz = pd.crosstab(dataframe["categoria_real"], dataframe["cluster"]).reindex(
        columns=range(12),
        fill_value=0,
    )
    mapeamento = {}
    resumos = []
    for cluster_id in range(12):
        contagens = matriz[cluster_id]
        categoria = contagens.idxmax()
        quantidade_categoria = int(contagens.loc[categoria])
        quantidade_total = int(contagens.sum())
        pureza = quantidade_categoria / quantidade_total if quantidade_total else 0.0
        rotulo = f"{categoria} ({cluster_id})"
        mapeamento[cluster_id] = rotulo
        resumos.append(
            {
                "cluster": cluster_id,
                "rotulo": rotulo,
                "categoria_majoritaria": categoria,
                "quantidade_noticias": quantidade_total,
                "quantidade_categoria_majoritaria": quantidade_categoria,
                "pureza_categoria": round(pureza, 6),
                "coesao_media_cosseno": round(
                    calcular_coesao_cluster(embeddings, np.where(clusters == cluster_id)[0]),
                    6,
                ),
            }
        )

    dataframe["cluster_label"] = dataframe["cluster"].map(mapeamento)
    dataframe["cluster_category"] = dataframe["cluster_label"].str.replace(
        r" \(\d+\)$",
        "",
        regex=True,
    )
    coordenadas, variancia = reduzir_array_para_tres_dimensoes(embeddings)
    dataframe["cluster_x"] = coordenadas[:, 0]
    dataframe["cluster_y"] = coordenadas[:, 1]
    dataframe["cluster_z"] = coordenadas[:, 2]

    PROCESSED_PATH.mkdir(parents=True, exist_ok=True)
    REPORTS_PATH.mkdir(parents=True, exist_ok=True)
    dataframe.to_json(
        WORD2VEC_CLUSTERS_JSONL_PATH,
        orient="records",
        lines=True,
        force_ascii=False,
        date_format="iso",
    )
    pd.DataFrame(resumos).to_csv(
        WORD2VEC_CLUSTER_SUMMARY_PATH,
        index=False,
        encoding="utf-8",
    )
    gerar_html_clusters_generico(
        dataframe,
        variancia,
        WORD2VEC_CLUSTER_HTML_PATH,
        WORD2VEC_CLUSTER_3D_HTML_PATH,
        "Clusters das noticias - Word2Vec k=12",
        "Word2Vec",
    )

    resumo = {
        "documents": int(len(dataframe)),
        "representation": "word2vec",
        "selected_clusters": 12,
        "silhouette": round(
            float(silhouette_score(embeddings, clusters, metric="cosine")),
            6,
        ),
        "pca_explained_variance": [round(float(valor), 6) for valor in variancia],
        "html_2d": WORD2VEC_CLUSTER_HTML_PATH.name,
        "html_3d": WORD2VEC_CLUSTER_3D_HTML_PATH.name,
        "summary": WORD2VEC_CLUSTER_SUMMARY_PATH.name,
    }
    print("Visualizacao Word2Vec k=12 concluida.")
    print(f"Silhouette: {resumo['silhouette']}")
    print(f"Visualizacao 2D: {WORD2VEC_CLUSTER_HTML_PATH}")
    print(f"Visualizacao 3D: {WORD2VEC_CLUSTER_3D_HTML_PATH}")
    return dataframe, resumo


if __name__ == "__main__":
    agrupar_base_existente()
