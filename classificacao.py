"""Classificacao das categorias das noticias com TF-IDF e Regressao Logistica."""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from representacao_textual import carregar_base_nlp


RANDOM_STATE = 42
MINIMO_EXEMPLOS_POR_CATEGORIA = 30
PROJECT_DIR = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_DIR / "data/processed/modelo_classificacao.joblib"
REPORT_PATH = PROJECT_DIR / "reports/classification_report.csv"


def preparar_dados(dataframe):
    dados = dataframe.dropna(subset=["title", "content", "category"]).copy()
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


def treinar_classificador(dataframe):
    dados = preparar_dados(dataframe)
    X_train, X_test, y_train, y_test = train_test_split(
        dados["texto"],
        dados["categoria"],
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=dados["categoria"],
    )

    modelo = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    min_df=2,
                    max_df=0.95,
                    ngram_range=(1, 2),
                    max_features=20_000,
                ),
            ),
            (
                "classificador",
                LogisticRegression(max_iter=1000, random_state=RANDOM_STATE),
            ),
        ]
    )
    modelo.fit(X_train, y_train)
    previsoes = modelo.predict(X_test)

    relatorio = pd.DataFrame(
        classification_report(
            y_test,
            previsoes,
            output_dict=True,
            zero_division=0,
        )
    ).transpose()

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo, MODEL_PATH)
    relatorio.to_csv(REPORT_PATH, encoding="utf-8")

    return modelo, relatorio, accuracy_score(y_test, previsoes), len(X_train), len(X_test)


def main():
    _, relatorio, acuracia, total_treino, total_teste = treinar_classificador(
        carregar_base_nlp()
    )
    print(f"Treino: {total_treino}")
    print(f"Teste: {total_teste}")
    print(f"Acuracia: {acuracia:.3f}\n")
    print(relatorio.round(3).to_string())
    print(f"\nModelo: {MODEL_PATH}")
    print(f"Relatorio: {REPORT_PATH}")


if __name__ == "__main__":
    main()
