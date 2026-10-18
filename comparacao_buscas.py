"""Compara representacoes e metricas de busca em uma unica matriz."""

from pathlib import Path

import pandas as pd

from busca import buscar
from metricas_busca import METRICAS


REPRESENTACOES = ("bow", "tfidf", "word2vec", "bert")
CONSULTAS_PADRAO = ("acidente no centro", "aniversário", "oktoberfest")
PROJECT_DIR = Path(__file__).resolve().parent
MATRIZ_PATH = PROJECT_DIR / "reports/comparacao_buscas.csv"
TOPK_ANALYSIS_PATH = PROJECT_DIR / "reports/busca_topk_avaliacao.csv"


def gerar_matriz_comparacao(consulta, top_k=3):
    linhas = []

    for metrica in METRICAS:
        resultados = {
            representacao: buscar(
                consulta,
                metodo=representacao,
                top_k=top_k,
                metrica=metrica,
            )
            for representacao in REPRESENTACOES
        }

        quantidade_resultados = min(len(resultado) for resultado in resultados.values())
        for posicao in range(quantidade_resultados):
            linha = {
                "consulta": consulta,
                "metrica": metrica,
                "posicao": posicao + 1,
            }
            for representacao, resultado in resultados.items():
                noticia = resultado.iloc[posicao]
                linha[f"{representacao}_score"] = noticia["score"]
                linha[f"{representacao}_titulo"] = noticia["title"]
                linha[f"{representacao}_categoria"] = noticia["category"]
                linha[f"{representacao}_url"] = noticia["url"]
            linhas.append(linha)

    matriz = pd.DataFrame(linhas)
    MATRIZ_PATH.parent.mkdir(parents=True, exist_ok=True)
    matriz.to_csv(MATRIZ_PATH, index=False, encoding="utf-8-sig")
    return matriz


def resumir_resultado_busca(resultado, consulta, representacao, metrica, top_k):
    categorias = resultado["category"].fillna("Sem categoria").astype(str)
    categoria_dominante = categorias.value_counts().idxmax()
    return {
        "consulta": consulta,
        "top_k": top_k,
        "metrica": metrica,
        "representacao": representacao,
        "score_medio": round(float(resultado["score"].mean()), 6),
        "categoria_dominante": categoria_dominante,
        "proporcao_categoria_dominante": round(
            float((categorias == categoria_dominante).mean()),
            6,
        ),
        "categorias_retornadas": "; ".join(
            f"{categoria}: {quantidade}"
            for categoria, quantidade in categorias.value_counts().items()
        ),
        "titulos": " | ".join(resultado["title"].astype(str).tolist()),
    }


def gerar_avaliacao_topk(
    consultas=CONSULTAS_PADRAO,
    top_ks=(3, 5),
    metricas=("cosseno",),
):
    linhas = []
    for consulta in consultas:
        for metrica in metricas:
            for representacao in REPRESENTACOES:
                maior_top_k = max(top_ks)
                resultado = buscar(
                    consulta,
                    metodo=representacao,
                    top_k=maior_top_k,
                    metrica=metrica,
                )
                for top_k in top_ks:
                    linhas.append(
                        resumir_resultado_busca(
                            resultado.head(top_k),
                            consulta,
                            representacao,
                            metrica,
                            top_k,
                        )
                    )

    avaliacao = pd.DataFrame(linhas)
    TOPK_ANALYSIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    avaliacao.to_csv(TOPK_ANALYSIS_PATH, index=False, encoding="utf-8-sig")
    return avaliacao


def imprimir_comparacao(matriz):
    colunas = [
        "metrica",
        "posicao",
        "bow_titulo",
        "tfidf_titulo",
        "word2vec_titulo",
        "bert_titulo",
    ]
    print(matriz[colunas].to_string(index=False))
    print(f"\nMatriz completa: {MATRIZ_PATH}")


def main():
    consulta = input("Digite a consulta: ").strip()
    imprimir_comparacao(gerar_matriz_comparacao(consulta))
    avaliacao = gerar_avaliacao_topk([consulta])
    print(f"Avaliacao top-k: {TOPK_ANALYSIS_PATH}")
    print(avaliacao.to_string(index=False))


if __name__ == "__main__":
    main()
