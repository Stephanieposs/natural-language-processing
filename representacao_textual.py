"""Funcoes simples para preparar os tokens usados nas representacoes."""

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent
NLP_JSONL_PATH = PROJECT_DIR / "data/processed/noticias_nlp.jsonl"
SEARCH_MANIFEST_PATH = PROJECT_DIR / "data/processed/indice_busca.json"
MAX_VECTOR_FEATURES = 15_000


def salvar_matriz_csv(matriz, vetorizador, caminho):
    """Transforma a matriz em DataFrame, como nos exemplos da disciplina."""
    dataframe = pd.DataFrame(
        matriz.toarray(),
        columns=vetorizador.get_feature_names_out(),
    )
    dataframe.insert(0, "id", range(len(dataframe)))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(caminho, index=False, encoding="utf-8-sig")


def carregar_matriz_csv(caminho):
    """Carrega o CSV e devolve somente as colunas da representacao."""
    dataframe = pd.read_csv(caminho)
    return dataframe.drop(columns="id").to_numpy()


def salvar_embeddings_csv(embeddings, caminho, prefixo):
    """Salva uma matriz densa com id e uma coluna para cada dimensao."""
    colunas = [f"{prefixo}_{indice:03d}" for indice in range(embeddings.shape[1])]
    dataframe = pd.DataFrame(embeddings, columns=colunas)
    dataframe.insert(0, "id", range(len(dataframe)))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(caminho, index=False, encoding="utf-8-sig")


def carregar_embeddings_csv(caminho):
    dataframe = pd.read_csv(caminho)
    return dataframe.drop(columns="id").to_numpy(dtype=np.float32)


def converter_para_lista(value):
    """Garante que os tokens armazenados na base sejam uma lista."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return [str(token) for token in value if str(token).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else value.split()
        except json.JSONDecodeError:
            return value.split()
    return []


def analisar_tokens(tokens):
    """Entrega ao vetorizador os tokens que ja foram preparados."""
    return tokens


def construir_corpus(dataframe):
    corpus = dataframe["tokens_sem_stopwords"].apply(converter_para_lista).tolist()
    if len(corpus) < 3:
        raise ValueError("Sao necessarias pelo menos tres noticias para vetorizar.")
    if sum(bool(documento) for documento in corpus) < 3:
        raise ValueError("Ha menos de tres noticias com tokens validos.")
    return corpus


def parametros_vetorizacao():
    return {
        "analyzer": analisar_tokens,
        "min_df": 2,
        "max_features": MAX_VECTOR_FEATURES,
    }


def carregar_base_nlp():
    if not NLP_JSONL_PATH.exists():
        raise FileNotFoundError(
            f"Base de PLN nao encontrada em {NLP_JSONL_PATH}. Execute primeiro o pipeline."
        )
    return pd.read_json(NLP_JSONL_PATH, lines=True)


def calcular_hash_base(dataframe):
    """Identifica a versao da base sem depender da ordem das colunas."""
    identificadores = dataframe.get("content_hash", dataframe["url"]).fillna("")
    conteudo = "\n".join(str(valor) for valor in identificadores)
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def carregar_manifest_indices():
    if not SEARCH_MANIFEST_PATH.exists():
        return {}
    return json.loads(SEARCH_MANIFEST_PATH.read_text(encoding="utf-8"))


def salvar_manifest_indices(manifesto):
    SEARCH_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEARCH_MANIFEST_PATH.write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
