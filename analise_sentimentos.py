"""Analise de sentimentos baseada em lexico para as noticias."""

import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from representacao_textual import (
    calcular_hash_base,
    carregar_base_nlp,
    converter_para_lista,
)


PROJECT_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_DIR / "data/processed"
REPORTS_DIR = PROJECT_DIR / "reports"
CLUSTERS_PATH = PROCESSED_DIR / "noticias_clusters.jsonl"
SENTIMENTS_JSONL_PATH = PROCESSED_DIR / "noticias_sentimentos.jsonl"
SENTIMENT_SUMMARY_PATH = REPORTS_DIR / "sentiment_summary.csv"
SENTIMENT_CATEGORY_PATH = REPORTS_DIR / "sentiment_by_category.csv"
SENTIMENT_CLUSTER_PATH = REPORTS_DIR / "sentiment_by_cluster.csv"
SUMMARY_PATH = REPORTS_DIR / "summary.json"

POSITIVE_WORDS = {
    "abertura": 0.7,
    "acolhimento": 1.0,
    "acolhedor": 1.0,
    "ajuda": 0.8,
    "apoio": 0.8,
    "aprovar": 0.8,
    "aprovado": 0.8,
    "aniversariante": 1.0,
    "aniversario": 1.0,
    "beneficio": 1.0,
    "celebrar": 1.0,
    "certificado": 0.7,
    "comemoracao": 0.9,
    "comemorar": 0.9,
    "conquista": 1.2,
    "conquistar": 1.1,
    "conscientizacao": 0.6,
    "cuidado": 0.7,
    "desconto": 0.7,
    "destaque": 0.6,
    "doacao": 0.8,
    "educacao": 0.5,
    "esperanca": 1.0,
    "festival": 0.7,
    "felicidade": 1.0,
    "felicidades": 1.0,
    "festa": 0.8,
    "fortalecer": 0.8,
    "gratuito": 0.9,
    "inaugurar": 0.9,
    "inclusao": 0.9,
    "inovacao": 0.8,
    "investimento": 0.8,
    "lazer": 0.7,
    "medalha": 1.1,
    "melhoria": 1.0,
    "melhorar": 1.0,
    "oportunidade": 0.9,
    "parabens": 1.0,
    "premiacao": 1.1,
    "premiado": 1.1,
    "premio": 1.1,
    "prevenir": 0.6,
    "promover": 0.6,
    "qualificacao": 0.8,
    "recuperacao": 0.9,
    "seguranca": 0.5,
    "solidariedade": 1.0,
    "sucesso": 1.2,
    "vencedor": 1.2,
    "vitoria": 1.2,
}

NEGATIVE_WORDS = {
    "acidente": -1.1,
    "alerta": -0.8,
    "ameaca": -1.0,
    "assalto": -1.3,
    "bloqueio": -0.7,
    "cancelamento": -0.8,
    "chuva": -0.5,
    "crime": -1.2,
    "crise": -1.1,
    "dano": -0.9,
    "desaparecido": -1.1,
    "deslizamento": -1.2,
    "dificuldade": -0.8,
    "doenca": -1.0,
    "emergencia": -1.0,
    "estelionato": -1.3,
    "falecido": -1.5,
    "falecidos": -1.5,
    "ferido": -1.1,
    "ferimentos": -1.1,
    "fraude": -1.2,
    "furto": -1.3,
    "grave": -1.0,
    "homicidio": -1.6,
    "incendio": -1.3,
    "instavel": -0.6,
    "investigacao": -0.6,
    "morte": -1.6,
    "morrer": -1.6,
    "obito": -1.6,
    "ocorrencia": -0.6,
    "perigo": -1.0,
    "prejuizo": -1.0,
    "prisao": -1.2,
    "preso": -1.2,
    "problema": -0.8,
    "queda": -0.8,
    "risco": -0.9,
    "roubo": -1.3,
    "temporal": -1.0,
    "trafico": -1.3,
    "transtorno": -0.8,
    "urgencia": -0.7,
    "vitima": -1.2,
    "vitimas": -1.2,
}

PHRASE_WEIGHTS = {
    "entrada gratuita": 1.0,
    "sem ferimentos": 0.8,
    "sem vitimas": 0.9,
    "saude mental": 0.4,
    "chuva forte": -1.0,
    "em estado grave": -1.3,
    "ferimentos graves": -1.4,
    "foi preso": -1.2,
    "mandado de prisao": -1.1,
    "morreu no local": -1.8,
    "risco de temporais": -1.0,
}

NEGATIONS = {"nao", "nunca", "jamais", "nem", "sem"}
INTENSIFIERS = {"muito", "muita", "muitos", "muitas", "extremamente", "bastante"}
DIMINISHERS = {"pouco", "pouca", "leves", "leve", "fraco", "fraca"}


def normalizar_texto(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto.casefold()


def normalizar_token(token):
    token = normalizar_texto(token)
    return re.sub(r"[^a-z]+", "", token)


def preparar_lexico(lexico):
    return {normalizar_token(termo): peso for termo, peso in lexico.items()}


POSITIVE_LEXICON = preparar_lexico(POSITIVE_WORDS)
NEGATIVE_LEXICON = preparar_lexico(NEGATIVE_WORDS)
SENTIMENT_LEXICON = {**POSITIVE_LEXICON, **NEGATIVE_LEXICON}
NORMALIZED_PHRASES = {
    " ".join(normalizar_token(token) for token in frase.split()): peso
    for frase, peso in PHRASE_WEIGHTS.items()
}


def montar_texto_noticia(registro):
    titulo = str(registro.get("title") or "").strip()
    conteudo = str(registro.get("content") or "").strip()
    return f"{titulo} {conteudo}".strip()


def obter_tokens(registro):
    tokens = converter_para_lista(registro.get("tokens_normalizados", []))
    if not tokens:
        tokens = re.findall(r"[^\W\d_]+", montar_texto_noticia(registro).casefold())
    return [normalizar_token(token) for token in tokens if normalizar_token(token)]


def ajustar_por_contexto(tokens, indice, peso):
    janela = tokens[max(0, indice - 3) : indice]
    if any(token in NEGATIONS for token in janela):
        peso *= -0.8
    if any(token in INTENSIFIERS for token in janela[-2:]):
        peso *= 1.4
    if any(token in DIMINISHERS for token in janela[-2:]):
        peso *= 0.7
    return peso


def pontuar_tokens(tokens):
    pesos = []
    for indice, token in enumerate(tokens):
        if token not in SENTIMENT_LEXICON:
            continue
        peso = ajustar_por_contexto(tokens, indice, SENTIMENT_LEXICON[token])
        pesos.append((token, peso))
    return pesos


def pontuar_frases(tokens):
    texto = " " + " ".join(tokens) + " "
    pesos = []
    for frase, peso in NORMALIZED_PHRASES.items():
        if not frase.strip():
            continue
        ocorrencias = texto.count(f" {frase} ")
        pesos.extend((frase.replace(" ", "_"), peso) for _ in range(ocorrencias))
    return pesos


def classificar_sentimento(score):
    if score >= 0.15:
        return "positivo"
    if score <= -0.15:
        return "negativo"
    return "neutro"


def top_termos(pesos, positivo=True, limite=8):
    selecionados = [(termo, peso) for termo, peso in pesos if (peso > 0) == positivo]
    contador = Counter(termo for termo, _ in selecionados)
    return "; ".join(
        f"{termo}: {quantidade}" for termo, quantidade in contador.most_common(limite)
    )


def analisar_registro(document_id, registro):
    tokens = obter_tokens(registro)
    pesos = pontuar_tokens(tokens) + pontuar_frases(tokens)
    positivo = sum(peso for _, peso in pesos if peso > 0)
    negativo = sum(-peso for _, peso in pesos if peso < 0)
    total = positivo + negativo
    score = (positivo - negativo) / total if total else 0.0

    return {
        "document_id": int(document_id),
        "title": registro.get("title", ""),
        "published_at": registro.get("published_at", ""),
        "category": registro.get("category", ""),
        "url": registro.get("url", ""),
        "content_hash": registro.get("content_hash", ""),
        "sentiment_label": classificar_sentimento(score),
        "sentiment_score": round(float(score), 6),
        "positive_score": round(float(positivo), 6),
        "negative_score": round(float(negativo), 6),
        "sentiment_terms": int(len(pesos)),
        "positive_terms": top_termos(pesos, positivo=True),
        "negative_terms": top_termos(pesos, positivo=False),
    }


def normalizar_categoria(categorias):
    return (
        categorias.fillna("Sem categoria")
        .astype(str)
        .str.split(",")
        .str[0]
        .str.strip()
        .replace("", "Sem categoria")
    )


def adicionar_clusters(dataframe, sentimentos):
    if not CLUSTERS_PATH.exists():
        return sentimentos
    clusters = pd.read_json(CLUSTERS_PATH, lines=True)
    if len(clusters) != len(dataframe):
        return sentimentos
    if calcular_hash_base(clusters) != calcular_hash_base(dataframe):
        return sentimentos
    for coluna in ("cluster", "cluster_label", "cluster_category"):
        if coluna in clusters:
            sentimentos[coluna] = clusters[coluna].values
    return sentimentos


def resumir_por_grupo(dataframe, coluna):
    if coluna not in dataframe:
        return pd.DataFrame()
    tabela = (
        dataframe.groupby(coluna, dropna=False)
        .agg(
            quantidade=("document_id", "count"),
            media_score=("sentiment_score", "mean"),
            termos_sentimento=("sentiment_terms", "sum"),
        )
        .reset_index()
    )
    distribuicao = pd.crosstab(dataframe[coluna], dataframe["sentiment_label"])
    for rotulo in ("positivo", "neutro", "negativo"):
        if rotulo not in distribuicao:
            distribuicao[rotulo] = 0
    tabela = tabela.merge(
        distribuicao[["positivo", "neutro", "negativo"]].reset_index(),
        on=coluna,
        how="left",
    )
    tabela["media_score"] = tabela["media_score"].round(6)
    return tabela.sort_values("quantidade", ascending=False)


def salvar_jsonl(dataframe, caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_json(
        caminho,
        orient="records",
        lines=True,
        force_ascii=False,
        date_format="iso",
    )


def atualizar_resumo_geral(resumo_sentimentos):
    resumo = {}
    if SUMMARY_PATH.exists():
        resumo = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    resumo["sentiment_analysis"] = resumo_sentimentos
    SUMMARY_PATH.write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def analisar_sentimentos(dataframe=None):
    dataframe = carregar_base_nlp() if dataframe is None else dataframe.copy()
    dataframe = dataframe.reset_index(drop=True)
    registros = [
        analisar_registro(document_id, registro)
        for document_id, registro in dataframe.iterrows()
    ]
    sentimentos = pd.DataFrame(registros)
    sentimentos["categoria_normalizada"] = normalizar_categoria(sentimentos["category"])
    sentimentos = adicionar_clusters(dataframe, sentimentos)

    resumo_geral = pd.DataFrame(
        [
            {
                "total_noticias": int(len(sentimentos)),
                "media_score": round(float(sentimentos["sentiment_score"].mean()), 6),
                "positivas": int((sentimentos["sentiment_label"] == "positivo").sum()),
                "neutras": int((sentimentos["sentiment_label"] == "neutro").sum()),
                "negativas": int((sentimentos["sentiment_label"] == "negativo").sum()),
                "termos_sentimento": int(sentimentos["sentiment_terms"].sum()),
            }
        ]
    )
    resumo_categorias = resumir_por_grupo(sentimentos, "categoria_normalizada")
    resumo_clusters = resumir_por_grupo(sentimentos, "cluster")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    salvar_jsonl(sentimentos, SENTIMENTS_JSONL_PATH)
    resumo_geral.to_csv(SENTIMENT_SUMMARY_PATH, index=False, encoding="utf-8")
    resumo_categorias.to_csv(SENTIMENT_CATEGORY_PATH, index=False, encoding="utf-8")
    if not resumo_clusters.empty:
        resumo_clusters.to_csv(SENTIMENT_CLUSTER_PATH, index=False, encoding="utf-8")

    distribuicao = sentimentos["sentiment_label"].value_counts().to_dict()
    resumo = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "documents": int(len(sentimentos)),
        "dataset_hash": calcular_hash_base(dataframe),
        "method": "lexico_com_negacao_intensidade_e_frases",
        "average_score": round(float(sentimentos["sentiment_score"].mean()), 6),
        "distribution": {
            "positivo": int(distribuicao.get("positivo", 0)),
            "neutro": int(distribuicao.get("neutro", 0)),
            "negativo": int(distribuicao.get("negativo", 0)),
        },
        "files": {
            "sentiments": SENTIMENTS_JSONL_PATH.name,
            "summary": SENTIMENT_SUMMARY_PATH.name,
            "by_category": SENTIMENT_CATEGORY_PATH.name,
            "by_cluster": SENTIMENT_CLUSTER_PATH.name
            if SENTIMENT_CLUSTER_PATH.exists()
            else None,
        },
    }
    atualizar_resumo_geral(resumo)
    return sentimentos, resumo_geral, resumo_categorias, resumo_clusters, resumo


def main():
    sentimentos, resumo_geral, resumo_categorias, resumo_clusters, resumo = (
        analisar_sentimentos()
    )
    print(
        f"Analise de sentimentos concluida: {resumo['documents']} noticias "
        f"({resumo['distribution']})."
    )
    print(f"Resultados: {SENTIMENTS_JSONL_PATH}")
    print(f"Resumo geral: {SENTIMENT_SUMMARY_PATH}")
    print(f"Resumo por categoria: {SENTIMENT_CATEGORY_PATH}")
    if not resumo_clusters.empty:
        print(f"Resumo por cluster: {SENTIMENT_CLUSTER_PATH}")
    print("\nResumo geral:")
    print(resumo_geral.to_string(index=False))
    print("\nCategorias com mais noticias:")
    print(resumo_categorias.head(15).to_string(index=False))
    print("\nNoticias mais negativas:")
    print(
        sentimentos.sort_values("sentiment_score")
        .head(10)[["sentiment_score", "sentiment_label", "category", "title"]]
        .to_string(index=False)
    )
    print("\nNoticias mais positivas:")
    print(
        sentimentos.sort_values("sentiment_score", ascending=False)
        .head(10)[["sentiment_score", "sentiment_label", "category", "title"]]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
