"""Geracao da representacao TF-IDF das noticias."""

from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer

from representacao_textual import (
    carregar_base_nlp,
    construir_corpus,
    parametros_vetorizacao,
    salvar_matriz_csv,
)


PROJECT_DIR = Path(__file__).resolve().parent
TFIDF_MATRIX_PATH = PROJECT_DIR / "data/processed/tfidf_matrix.csv"
TFIDF_VECTORIZER_PATH = PROJECT_DIR / "data/processed/vectorizer_tfidf.joblib"


def gerar_tfidf(corpus):
    vectorizer = TfidfVectorizer(**parametros_vetorizacao())
    matrix = vectorizer.fit_transform(corpus)

    TFIDF_MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    salvar_matriz_csv(matrix, vectorizer, TFIDF_MATRIX_PATH)
    joblib.dump(vectorizer, TFIDF_VECTORIZER_PATH)
    return vectorizer, matrix


def main():
    dataframe = carregar_base_nlp()
    _, matrix = gerar_tfidf(construir_corpus(dataframe))
    print(
        f"TF-IDF concluido: {matrix.shape[0]} documentos, "
        f"{matrix.shape[1]} atributos."
    )
    print(f"Matriz: {TFIDF_MATRIX_PATH}")


if __name__ == "__main__":
    main()
