import json

import numpy as np
import pandas as pd
import pytest

import clustering


@pytest.fixture
def base_visualizacao(tmp_path, monkeypatch):
    rng = np.random.default_rng(42)
    matriz = np.vstack([
        rng.normal([5, 1, 1, 1], .12, (6, 4)),
        rng.normal([1, 5, 1, 1], .12, (6, 4)),
    ])
    dados = pd.DataFrame({
        "title": [f"Noticia {i}" for i in range(12)],
        "category": ["A"] * 6 + ["B"] * 6,
        "published_at": ["2026-09-21"] * 12,
        "url": [f"https://exemplo.local/{i}" for i in range(12)],
        "content_hash": [str(i) for i in range(12)],
    })
    caminho = tmp_path / "vetores.csv"
    vetores = pd.DataFrame(matriz)
    vetores.insert(0, "id", range(12))
    vetores.to_csv(caminho, index=False)
    monkeypatch.setattr(clustering, "BOW_MATRIX_PATH", caminho)
    monkeypatch.setattr(clustering, "BERT_EMBEDDINGS_PATH", caminho)
    monkeypatch.setattr(clustering, "PROCESSED_PATH", tmp_path / "processed")
    monkeypatch.setattr(clustering, "REPORTS_PATH", tmp_path / "reports")
    manifesto = {"documents": 12, "dataset_hash": clustering.calcular_hash_base(dados)}
    monkeypatch.setattr(clustering, "carregar_manifest_indices", lambda: {"lexical": manifesto, "semantic": manifesto})
    return dados, caminho, tmp_path


@pytest.mark.parametrize("representacao", ["bow", "bert"])
def test_salva_grupos_pca_e_graficos_consistentes(base_visualizacao, representacao):
    dados, _, pasta = base_visualizacao
    resultado, resumo = clustering.gerar_visualizacao_representacao(representacao, 2, dados)
    stem = f"{representacao}_k2"
    salvo = pd.read_json(pasta / "processed" / f"noticias_clusters_{stem}.jsonl", lines=True)
    assert len(salvo) == len(dados)
    assert salvo["url"].tolist() == dados["url"].tolist()
    assert salvo["cluster"].nunique() == 2
    assert np.isfinite(salvo[["cluster_x", "cluster_y", "cluster_z"]]).all().all()
    assert np.allclose(salvo[["cluster_x", "cluster_y", "cluster_z"]], resultado[["cluster_x", "cluster_y", "cluster_z"]])
    assert resumo["pureza_categoria"] == 1
    assert resumo["silhouette_cosseno"] > .9
    assert len(resumo["pca_explained_variance"]) == 3
    assert "scatter3d" in (pasta / "reports" / resumo["html_3d"]).read_text(encoding="utf-8")
    assert "PCA 1" in (pasta / "reports" / resumo["html_2d"]).read_text(encoding="utf-8")
    metadados = json.loads((pasta / "reports" / f"cluster_visualization_{stem}.json").read_text(encoding="utf-8"))
    assert metadados["dataset_hash"] == clustering.calcular_hash_base(dados)
    distancias = pd.read_csv(pasta / "reports" / resumo["centroid_distances"], index_col=0).to_numpy()
    assert np.allclose(distancias, distancias.T)
    assert np.allclose(np.diag(distancias), 0, atol=1e-6)


def test_rejeita_mesmo_total_com_documentos_trocados(base_visualizacao):
    dados, _, _ = base_visualizacao
    dados.loc[0, "content_hash"] = "noticia-diferente"
    with pytest.raises(RuntimeError, match="nao correspondem"):
        clustering.gerar_visualizacao_representacao("bow", 2, dados)


def test_rejeita_vetores_fora_da_ordem(base_visualizacao):
    dados, caminho, _ = base_visualizacao
    pd.read_csv(caminho).iloc[::-1].to_csv(caminho, index=False)
    with pytest.raises(ValueError, match="ordem dos ids"):
        clustering.gerar_visualizacao_representacao("bert", 2, dados)
