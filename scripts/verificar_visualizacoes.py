"""Verifica os arquivos gerados para as visualizacoes BoW/BERT da Unidade 3."""

import base64
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from representacao_textual import calcular_hash_base, carregar_base_nlp


def quantidade(vetor):
    if isinstance(vetor, list):
        return len(vetor)
    return len(np.frombuffer(base64.b64decode(vetor["bdata"]), dtype=vetor["dtype"]))


def main():
    comparacao = pd.read_csv(ROOT / "reports/cluster_representations_comparison.csv")
    base = carregar_base_nlp()
    decoder = json.JSONDecoder()
    for metodo in ("bow", "bert"):
        meta = json.loads((ROOT / f"reports/cluster_visualization_{metodo}_k13.json").read_text(encoding="utf-8"))
        assert meta["dataset_hash"] == calcular_hash_base(base)
        anterior = comparacao[(comparacao.representacao == metodo) & (comparacao.clusters == 13)].iloc[0]
        for chave in ("silhouette_cosseno", "pureza_categoria", "distancia_media_centroides", "distancia_minima_centroides"):
            assert abs(meta[chave] - anterior[chave]) < 1e-6, (metodo, chave)
        for dimensao, chave in ((2, "html_2d"), (3, "html_3d")):
            html = (ROOT / "reports" / meta[chave]).read_text(encoding="utf-8")
            match = re.search(r'Plotly.newPlot\(\s*"[^"]+"\s*,\s*', html)
            assert match
            traces, _ = decoder.raw_decode(html[match.end():])
            assert len(traces) == 13
            assert sum(quantidade(t["x"]) for t in traces) == len(base)
            assert all(t["type"] == ("scatter3d" if dimensao == 3 else "scatter") for t in traces)
        print(f"{metodo}: HTML 2D/3D validos, {len(base)} noticias e metricas iguais a comparacao salva.")


if __name__ == "__main__":
    main()
