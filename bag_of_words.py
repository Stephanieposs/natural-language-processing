"""Geracao da representacao Bag of Words das noticias."""

from pathlib import Path

import joblib
from sklearn.feature_extraction.text import CountVectorizer

from representacao_textual import (
    carregar_base_nlp,
    construir_corpus,
    parametros_vetorizacao,
    salvar_matriz_csv,
)


PROJECT_DIR = Path(__file__).resolve().parent
BOW_MATRIX_PATH = PROJECT_DIR / "data/processed/bow_matrix.csv"
BOW_VECTORIZER_PATH = PROJECT_DIR / "data/processed/vectorizer_bow.joblib"


def gerar_bag_of_words(corpus):
    vectorizer = CountVectorizer(**parametros_vetorizacao())
    matrix = vectorizer.fit_transform(corpus)

    BOW_MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    salvar_matriz_csv(matrix, vectorizer, BOW_MATRIX_PATH)
    joblib.dump(vectorizer, BOW_VECTORIZER_PATH)
    return vectorizer, matrix


def main():
    dataframe = carregar_base_nlp()
    _, matrix = gerar_bag_of_words(construir_corpus(dataframe))
    print(
        f"Bag of Words concluido: {matrix.shape[0]} documentos, "
        f"{matrix.shape[1]} atributos."
    )
    print(f"Matriz: {BOW_MATRIX_PATH}")


if __name__ == "__main__":
    main()
