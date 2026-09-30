"""Grafico interativo dos clusters, seguindo o exemplo com Plotly."""

from pathlib import Path

import plotly.express as px


PROJECT_DIR = Path(__file__).resolve().parent
REPORTS_PATH = PROJECT_DIR / "reports"
CLUSTER_HTML_PATH = REPORTS_PATH / "clusters_tfidf.html"
CLUSTER_3D_HTML_PATH = REPORTS_PATH / "clusters_tfidf_3d.html"


def gerar_html_clusters(dataframe, variancia_explicada):
    dados = dataframe.copy()
    dados["cluster"] = dados["cluster"].astype(str)
    eixo_x = f"PCA 1 ({variancia_explicada[0]:.2%})"
    eixo_y = f"PCA 2 ({variancia_explicada[1]:.2%})"
    eixo_z = f"PCA 3 ({variancia_explicada[2]:.2%})"
    explicacao = (
        "<br><sup>Eixos: componentes principais da matriz TF-IDF; "
        "percentual = variancia explicada.</sup>"
    )

    figura = px.scatter(
        dados,
        x="cluster_x",
        y="cluster_y",
        color="cluster",
        hover_name="title",
        hover_data={
            "category": True,
            "published_at": True,
            "cluster_label": True,
            "cluster_x": False,
            "cluster_y": False,
        },
        title="Clusters das noticias - TF-IDF projetado por PCA em 2D" + explicacao,
    )
    figura.update_traces(marker={"size": 8})
    figura.update_layout(
        xaxis_title=eixo_x,
        yaxis_title=eixo_y,
        legend_title="Cluster K-Means",
    )

    REPORTS_PATH.mkdir(parents=True, exist_ok=True)
    figura.write_html(CLUSTER_HTML_PATH, include_plotlyjs=True)

    figura_3d = px.scatter_3d(
        dados,
        x="cluster_x",
        y="cluster_y",
        z="cluster_z",
        color="cluster",
        hover_name="title",
        hover_data={
            "category": True,
            "published_at": True,
            "cluster_label": True,
            "cluster_x": False,
            "cluster_y": False,
            "cluster_z": False,
        },
        title="Clusters das noticias - TF-IDF projetado por PCA em 3D" + explicacao,
    )
    figura_3d.update_traces(marker={"size": 5})
    figura_3d.update_layout(
        scene={
            "xaxis_title": eixo_x,
            "yaxis_title": eixo_y,
            "zaxis_title": eixo_z,
        },
        legend_title="Cluster K-Means",
    )
    figura_3d.write_html(CLUSTER_3D_HTML_PATH, include_plotlyjs=True)
