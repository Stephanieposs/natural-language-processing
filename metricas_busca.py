"""Metricas usadas para comparar uma consulta com os documentos."""

from sklearn.metrics.pairwise import (
    cosine_similarity,
    euclidean_distances,
    manhattan_distances,
)


METRICAS = ("cosseno", "euclidiana", "manhattan")


def calcular_relevancia(vetor_consulta, matriz_documentos, metrica):
    if metrica == "cosseno":
        return cosine_similarity(vetor_consulta, matriz_documentos)[0]
    if metrica == "euclidiana":
        distancias = euclidean_distances(vetor_consulta, matriz_documentos)[0]
    elif metrica == "manhattan":
        distancias = manhattan_distances(vetor_consulta, matriz_documentos)[0]
    else:
        raise ValueError(f"Metrica invalida. Use: {', '.join(METRICAS)}.")

    return 1 / (1 + distancias)
