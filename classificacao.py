"""Classificacao das categorias das noticias com TF-IDF e Regressao Logistica."""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from bert import BERT_EMBEDDINGS_PATH
from representacao_textual import carregar_base_nlp, carregar_embeddings_csv
from word2vec import WORD2VEC_EMBEDDINGS_PATH


RANDOM_STATE = 42
MINIMO_EXEMPLOS_POR_CATEGORIA = 30
PROJECT_DIR = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_DIR / "data/processed/modelo_classificacao.joblib"
REPORT_PATH = PROJECT_DIR / "reports/classification_report.csv"
COMPARISON_PATH = PROJECT_DIR / "reports/classification_comparison.csv"
REPORTS_DIR = PROJECT_DIR / "reports"


def preparar_dados(dataframe):
    dados = dataframe.dropna(subset=["title", "content", "category"]).copy()
    dados["document_id"] = dados.index
    dados["texto"] = (
        dados["title"].astype(str).str.strip()
        + ". "
        + dados["content"].astype(str).str.strip()
    )
    dados["categoria"] = (
        dados["category"].astype(str).str.split(",").str[0].str.strip()
    )
    dados = dados[dados["texto"].str.len() > 0]
    dados = dados.drop_duplicates(subset=["texto", "categoria"])

    contagens = dados["categoria"].value_counts()
    categorias_validas = contagens[
        contagens >= MINIMO_EXEMPLOS_POR_CATEGORIA
    ].index
    return dados[dados["categoria"].isin(categorias_validas)].reset_index(drop=True)


def dividir_treino_teste(dados):
    indices = dados.index
    return train_test_split(
        indices,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=dados["categoria"],
    )


def modelo_lexico(representacao):
    if representacao == "bow":
        vetorizador = CountVectorizer(
            lowercase=True,
            min_df=2,
            max_df=0.95,
            ngram_range=(1, 2),
            max_features=20_000,
        )
    elif representacao == "tfidf":
        vetorizador = TfidfVectorizer(
            lowercase=True,
            min_df=2,
            max_df=0.95,
            ngram_range=(1, 2),
            max_features=20_000,
        )
    else:
        raise ValueError("Representacao lexica invalida.")

    return Pipeline(
        [
            (representacao, vetorizador),
            (
                "classificador",
                LogisticRegression(max_iter=1000, random_state=RANDOM_STATE),
            ),
        ]
    )


def modelo_denso():
    return Pipeline(
        [
            ("escala", StandardScaler()),
            (
                "classificador",
                LogisticRegression(max_iter=2000, random_state=RANDOM_STATE),
            ),
        ]
    )


def avaliar_previsoes(y_test, previsoes, representacao):
    relatorio = pd.DataFrame(
        classification_report(
            y_test,
            previsoes,
            output_dict=True,
            zero_division=0,
        )
    ).transpose()
    relatorio.insert(0, "representacao", representacao)
    return relatorio


def treinar_modelo_lexico(dados, treino, teste, representacao):
    modelo = modelo_lexico(representacao)
    modelo.fit(dados.loc[treino, "texto"], dados.loc[treino, "categoria"])
    previsoes = modelo.predict(dados.loc[teste, "texto"])
    return modelo, previsoes


def treinar_modelo_embedding(dados, treino, teste, caminho):
    embeddings = carregar_embeddings_csv(caminho)
    document_ids = dados["document_id"].to_numpy()
    matriz = embeddings[document_ids]
    modelo = modelo_denso()
    modelo.fit(matriz[treino], dados.loc[treino, "categoria"])
    previsoes = modelo.predict(matriz[teste])
    return modelo, previsoes


def treinar_classificador(dataframe):
    dados = preparar_dados(dataframe)
    treino, teste = dividir_treino_teste(dados)
    modelo, previsoes = treinar_modelo_lexico(dados, treino, teste, "tfidf")
    relatorio = avaliar_previsoes(dados.loc[teste, "categoria"], previsoes, "tfidf")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, MODEL_PATH)
    relatorio.to_csv(REPORT_PATH, encoding="utf-8")

    return (
        modelo,
        relatorio,
        accuracy_score(dados.loc[teste, "categoria"], previsoes),
        len(treino),
        len(teste),
    )


def comparar_representacoes_classificacao(dataframe):
    dados = preparar_dados(dataframe)
    treino, teste = dividir_treino_teste(dados)
    y_test = dados.loc[teste, "categoria"]
    resultados = []
    relatorios = []
    modelos = {}

    for representacao in ("bow", "tfidf"):
        modelo, previsoes = treinar_modelo_lexico(dados, treino, teste, representacao)
        modelos[representacao] = modelo
        metricas = classification_report(
            y_test,
            previsoes,
            output_dict=True,
            zero_division=0,
        )
        relatorio = pd.DataFrame(metricas).transpose()
        if representacao == "tfidf":
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            relatorio.to_csv(REPORT_PATH, encoding="utf-8")
        relatorio.insert(0, "representacao", representacao)
        relatorios.append(relatorio)
        resultados.append(
            {
                "representacao": representacao,
                "acuracia": round(float(accuracy_score(y_test, previsoes)), 6),
                "macro_f1": round(float(metricas["macro avg"]["f1-score"]), 6),
                "weighted_f1": round(float(metricas["weighted avg"]["f1-score"]), 6),
                "treino": len(treino),
                "teste": len(teste),
                "observacao": "",
            }
        )

    for representacao, caminho in (
        ("word2vec", WORD2VEC_EMBEDDINGS_PATH),
        ("bert", BERT_EMBEDDINGS_PATH),
    ):
        if not caminho.exists():
            resultados.append(
                {
                    "representacao": representacao,
                    "acuracia": None,
                    "macro_f1": None,
                    "weighted_f1": None,
                    "treino": len(treino),
                    "teste": len(teste),
                    "observacao": f"Embeddings ausentes em {caminho.name}.",
                }
            )
            continue
        modelo, previsoes = treinar_modelo_embedding(dados, treino, teste, caminho)
        modelos[representacao] = modelo
        relatorios.append(avaliar_previsoes(y_test, previsoes, representacao))
        metricas = classification_report(
            y_test,
            previsoes,
            output_dict=True,
            zero_division=0,
        )
        resultados.append(
            {
                "representacao": representacao,
                "acuracia": round(float(accuracy_score(y_test, previsoes)), 6),
                "macro_f1": round(float(metricas["macro avg"]["f1-score"]), 6),
                "weighted_f1": round(float(metricas["weighted avg"]["f1-score"]), 6),
                "treino": len(treino),
                "teste": len(teste),
                "observacao": "",
            }
        )

    comparacao = pd.DataFrame(resultados).sort_values(
        ["weighted_f1", "acuracia"],
        ascending=False,
        na_position="last",
    )
    relatorio_completo = pd.concat(relatorios)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    comparacao.to_csv(COMPARISON_PATH, index=False, encoding="utf-8")
    relatorio_completo.to_csv(
        REPORTS_DIR / "classification_reports_by_representation.csv",
        encoding="utf-8",
    )
    if "tfidf" in modelos:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(modelos["tfidf"], MODEL_PATH)
    return comparacao, relatorio_completo, len(treino), len(teste)


def main():
    comparacao, relatorio, total_treino, total_teste = (
        comparar_representacoes_classificacao(carregar_base_nlp())
    )
    print(f"Treino: {total_treino}")
    print(f"Teste: {total_teste}")
    print("\nComparacao por representacao:")
    print(comparacao.to_string(index=False))
    print("\nRelatorio detalhado:")
    print(relatorio.round(3).to_string())
    print(f"\nModelo: {MODEL_PATH}")
    print(f"Relatorio: {REPORT_PATH}")
    print(f"Comparacao: {COMPARISON_PATH}")


if __name__ == "__main__":
    main()
