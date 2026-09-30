"""Word2Vec com media dos vetores das palavras de cada noticia."""

from pathlib import Path

import numpy as np

from metricas_busca import calcular_relevancia
from representacao_textual import (
    carregar_base_nlp,
    carregar_embeddings_csv,
    construir_corpus,
    salvar_embeddings_csv,
)


PROJECT_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_DIR / "data/processed"
WORD2VEC_MODEL_PATH = PROCESSED_DIR / "modelo_word2vec.model"
WORD2VEC_EMBEDDINGS_PATH = PROCESSED_DIR / "embeddings_word2vec.csv"
WORD2VEC_VECTOR_SIZE = 190
WORD2VEC_EPOCHS = 200


def carregar_classe_word2vec():
    try:
        from gensim.models import Word2Vec
    except ImportError as error:
        raise RuntimeError("Instale a dependencia gensim para usar Word2Vec.") from error
    return Word2Vec


def vetor_documento_word2vec(tokens, modelo):
    vetores = [modelo.wv[token] for token in tokens if token in modelo.wv]
    if not vetores:
        return np.zeros(modelo.vector_size, dtype=np.float32)
    return np.mean(vetores, axis=0)


def gerar_indice_word2vec(dataframe, reutilizar=False):
    Word2Vec = carregar_classe_word2vec()
    corpus = construir_corpus(dataframe)

    if reutilizar and WORD2VEC_MODEL_PATH.exists() and WORD2VEC_EMBEDDINGS_PATH.exists():
        modelo = Word2Vec.load(str(WORD2VEC_MODEL_PATH))
        embeddings = carregar_embeddings_csv(WORD2VEC_EMBEDDINGS_PATH)
        reutilizar = (
            modelo.vector_size == WORD2VEC_VECTOR_SIZE
            and embeddings.shape == (len(dataframe), WORD2VEC_VECTOR_SIZE)
        )
        if reutilizar:
            print("Reutilizando o indice Word2Vec existente...", flush=True)

    if not reutilizar:
        print("Treinando Word2Vec...", flush=True)
        modelo = Word2Vec(
            sentences=corpus,
            vector_size=WORD2VEC_VECTOR_SIZE,
            window=5,
            min_count=1,
            sg=1,
            seed=42,
            workers=1,
            epochs=WORD2VEC_EPOCHS,
        )
        embeddings = np.vstack(
            [vetor_documento_word2vec(tokens, modelo) for tokens in corpus]
        )
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        modelo.save(str(WORD2VEC_MODEL_PATH))
        salvar_embeddings_csv(embeddings, WORD2VEC_EMBEDDINGS_PATH, "w2v")

    return {
        "vector_size": modelo.vector_size,
        "epochs": WORD2VEC_EPOCHS,
        "vocabulary_size": len(modelo.wv),
    }


def pontuar_word2vec(tokens_consulta, total_documentos, metrica="cosseno"):
    Word2Vec = carregar_classe_word2vec()
    if not WORD2VEC_MODEL_PATH.exists() or not WORD2VEC_EMBEDDINGS_PATH.exists():
        raise FileNotFoundError(
            "Indice Word2Vec ausente. Execute: python projeto_pln.py --indexar-busca"
        )

    modelo = Word2Vec.load(str(WORD2VEC_MODEL_PATH))
    embeddings = carregar_embeddings_csv(WORD2VEC_EMBEDDINGS_PATH)
    if embeddings.shape[0] != total_documentos:
        raise RuntimeError("O indice Word2Vec esta desatualizado.")

    vetor_consulta = vetor_documento_word2vec(tokens_consulta, modelo)
    return calcular_relevancia(
        vetor_consulta.reshape(1, -1), embeddings, metrica
    )


def main():
    dataframe = carregar_base_nlp()
    metadados = gerar_indice_word2vec(dataframe)
    print(
        f"Word2Vec concluido: {len(dataframe)} documentos, "
        f"{metadados['vocabulary_size']} termos no vocabulario."
    )


if __name__ == "__main__":
    main()
