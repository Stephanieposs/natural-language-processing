"""BERTimbau com mean pooling para representar cada noticia."""

from functools import lru_cache
from pathlib import Path

import numpy as np

from metricas_busca import calcular_relevancia
from representacao_textual import (
    carregar_base_nlp,
    carregar_embeddings_csv,
    salvar_embeddings_csv,
)


PROJECT_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_DIR / "data/processed"
BERT_EMBEDDINGS_PATH = PROCESSED_DIR / "embeddings_bert.csv"
BERT_MODEL_NAME = "neuralmind/bert-base-portuguese-cased"
BERT_MAX_LENGTH = 256
BERT_STRATEGY = "media_dos_blocos"


@lru_cache(maxsize=2)
def carregar_bert(local_files_only=False):
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as error:
        raise RuntimeError("Instale transformers e torch para usar BERT.") from error

    dispositivo = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizador = AutoTokenizer.from_pretrained(
        BERT_MODEL_NAME,
        do_lower_case=False,
        local_files_only=local_files_only,
    )
    modelo = AutoModel.from_pretrained(
        BERT_MODEL_NAME,
        local_files_only=local_files_only,
    ).to(dispositivo)
    modelo.eval()
    return tokenizador, modelo, dispositivo


def mean_pooling(last_hidden_state, attention_mask):
    import torch

    mascara = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    soma = torch.sum(last_hidden_state * mascara, dim=1)
    quantidade = torch.clamp(mascara.sum(dim=1), min=1e-9)
    return soma / quantidade


def dividir_texto_em_blocos(texto, tokenizador):
    """Divide textos longos para nao descartar o final da noticia."""
    token_ids = tokenizador.encode(texto, add_special_tokens=False)
    tamanho_bloco = BERT_MAX_LENGTH - 2
    if not token_ids:
        return [""]
    return [
        tokenizador.decode(token_ids[inicio : inicio + tamanho_bloco])
        for inicio in range(0, len(token_ids), tamanho_bloco)
    ]


def gerar_embeddings_bert(textos, tokenizador, modelo, dispositivo, batch_size=16):
    import torch

    blocos = []
    documentos_dos_blocos = []
    for indice, texto in enumerate(textos):
        trechos = dividir_texto_em_blocos(texto, tokenizador)
        blocos.extend(trechos)
        documentos_dos_blocos.extend([indice] * len(trechos))

    somas = np.zeros((len(textos), modelo.config.hidden_size), dtype=np.float32)
    quantidades = np.zeros(len(textos), dtype=np.int32)
    for inicio in range(0, len(blocos), batch_size):
        lote = blocos[inicio : inicio + batch_size]
        entradas = tokenizador(
            lote,
            padding=True,
            truncation=True,
            max_length=BERT_MAX_LENGTH,
            return_tensors="pt",
        )
        entradas = {chave: valor.to(dispositivo) for chave, valor in entradas.items()}
        with torch.no_grad():
            saida = modelo(**entradas)
        embeddings = mean_pooling(saida.last_hidden_state, entradas["attention_mask"])
        indices = documentos_dos_blocos[inicio : inicio + len(lote)]
        np.add.at(somas, indices, embeddings.cpu().numpy())
        np.add.at(quantidades, indices, 1)
    return somas / quantidades[:, None]


def textos_das_noticias(dataframe):
    return (
        dataframe["title"].fillna("") + ". " + dataframe["content"].fillna("")
    ).tolist()


def gerar_indice_bert(dataframe, reutilizar=False, metadados_anteriores=None):
    metadados_anteriores = metadados_anteriores or {}
    configuracao_compativel = (
        metadados_anteriores.get("max_length") == BERT_MAX_LENGTH
        and metadados_anteriores.get("strategy") == BERT_STRATEGY
    )
    if reutilizar and BERT_EMBEDDINGS_PATH.exists():
        embeddings = carregar_embeddings_csv(BERT_EMBEDDINGS_PATH)
        reutilizar = embeddings.shape == (len(dataframe), 768)
        reutilizar = reutilizar and configuracao_compativel
        if reutilizar:
            print("Reutilizando os embeddings BERTimbau existentes...", flush=True)

    if not reutilizar:
        print(f"Carregando o modelo BERTimbau: {BERT_MODEL_NAME}...", flush=True)
        tokenizador, modelo, dispositivo = carregar_bert()
        print("Gerando embeddings BERTimbau...", flush=True)
        embeddings = gerar_embeddings_bert(
            textos_das_noticias(dataframe), tokenizador, modelo, dispositivo
        )
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        salvar_embeddings_csv(embeddings, BERT_EMBEDDINGS_PATH, "bert")

    return {
        "enabled": True,
        "model": BERT_MODEL_NAME,
        "dimension": int(embeddings.shape[1]),
        "max_length": BERT_MAX_LENGTH,
        "strategy": BERT_STRATEGY,
    }


def pontuar_bert(consulta, total_documentos, metrica="cosseno"):
    if not BERT_EMBEDDINGS_PATH.exists():
        raise FileNotFoundError(
            "Indice BERT ausente. Execute --indexar-busca sem a opcao --sem-bert."
        )

    embeddings = carregar_embeddings_csv(BERT_EMBEDDINGS_PATH)
    if embeddings.shape[0] != total_documentos:
        raise RuntimeError("O indice BERT esta desatualizado.")

    tokenizador, modelo, dispositivo = carregar_bert(local_files_only=True)
    vetor_consulta = gerar_embeddings_bert(
        [consulta], tokenizador, modelo, dispositivo
    )[0]
    return calcular_relevancia(
        vetor_consulta.reshape(1, -1), embeddings, metrica
    )


def main():
    dataframe = carregar_base_nlp()
    metadados = gerar_indice_bert(dataframe)
    print(
        f"BERTimbau concluido: {len(dataframe)} documentos, "
        f"{metadados['dimension']} dimensoes."
    )


if __name__ == "__main__":
    main()
