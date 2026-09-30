"""Compara representacoes e metricas de busca em uma unica matriz."""

from pathlib import Path

import pandas as pd

from busca import buscar
from metricas_busca import METRICAS


REPRESENTACOES = ("bow", "tfidf", "word2vec", "bert")
PROJECT_DIR = Path(__file__).resolve().parent
MATRIZ_PATH = PROJECT_DIR / "reports/comparacao_buscas.csv"


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


if __name__ == "__main__":
    consulta = input("Digite a consulta: ").strip()
    imprimir_comparacao(gerar_matriz_comparacao(consulta))
