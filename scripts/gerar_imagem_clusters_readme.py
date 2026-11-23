"""Gera a imagem 2D dos dez clusters Word2Vec publicos usada no README."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web" / "data" / "results.json"
OUTPUT = ROOT / "docs" / "figures" / "clusters_word2vec_2d.png"
COLORS = [
    "#12635b", "#b74c37", "#536f9e", "#9a6231", "#72508d", "#5d7a37",
    "#aa5e83", "#2d8196", "#9e8d36", "#656b76", "#ba7862", "#36845c",
]


def main():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    result = data["word2vec_public_10"]
    points = result["points"]
    fig, ax = plt.subplots(figsize=(11, 7.3), dpi=170)
    fig.patch.set_facecolor("#f8faf9")
    ax.set_facecolor("#ffffff")

    for group in range(result["clusters"]):
        members = [point for point in points if point[2] == group]
        ax.scatter(
            [point[0] for point in members], [point[1] for point in members],
            s=13, alpha=0.48, color=COLORS[group % len(COLORS)],
            edgecolors="none", label=f"Grupo {group + 1} ({len(members)})",
            rasterized=True,
        )

    variance_x = f"{result['pca_variance'][0] * 100:.1f}".replace(".", ",")
    variance_y = f"{result['pca_variance'][1] * 100:.1f}".replace(".", ",")
    ax.set_xlabel(f"PCA 1 ({variance_x}% da variação)", labelpad=9)
    ax.set_ylabel(f"PCA 2 ({variance_y}% da variação)", labelpad=9)
    ax.grid(color="#e4eae7", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color("#a9bab5")
    ax.tick_params(colors="#52616a", labelsize=9)
    ax.set_title(
        f"Projeção PCA de {len(points):,} notícias públicas em {result['clusters']} grupos".replace(",", "."),
        loc="left", fontsize=12, color="#52616a", pad=14,
    )
    fig.suptitle("Clusters de notícias · Word2Vec + K-Means", x=0.08, y=0.975,
                 ha="left", fontsize=19, fontweight="bold", color="#0b2424")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=4,
              frameon=False, fontsize=9, markerscale=1.6, columnspacing=1.4)
    explained = f"{sum(result['pca_variance']) * 100:.1f}".replace(".", ",")
    fig.text(0.08, 0.025,
             f"K-Means treinado no recorte público; PCA da base válida. Cores indicam grupos, "
             f"não categorias. Os eixos mostram {explained}% da variação.",
             fontsize=9, color="#52616a")
    fig.subplots_adjust(left=0.09, right=0.985, top=0.84, bottom=0.26)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=170, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
