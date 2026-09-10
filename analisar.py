"""Analisa a base preparada: estatísticas, gráficos e conferência de qualidade.

Uso:
    python analisar.py
"""

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median

import matplotlib
matplotlib.use("Agg")  # gera as imagens sem precisar abrir janela
import matplotlib.pyplot as plt

ENTRADA_PADRAO = Path("dados/noticias_preparadas.jsonl")
PASTA_PADRAO = Path("relatorios")

CAMPOS_OBRIGATORIOS = ["titulo", "data", "categoria", "texto", "url"]


def carregar(arquivo):
    """Lê a base preparada."""
    with open(arquivo, encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def entender_data(texto):
    """Transforma o texto da data em data de verdade. Devolve None se não der."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None


def contar_por_categoria(noticias):
    """Quantas notícias em cada categoria."""
    return Counter(n["categoria"].strip() or "Sem categoria" for n in noticias)


def contar_por_mes(noticias):
    """Quantas notícias publicadas em cada mês."""
    contagem = Counter()
    for noticia in noticias:
        data = entender_data(noticia["data"])
        if data:
            contagem[data.strftime("%Y-%m")] += 1
    return dict(sorted(contagem.items()))


def estatisticas_de_tamanho(noticias):
    """Menor, maior, média e mediana de palavras por notícia."""
    tamanhos = [n["palavras"] for n in noticias]
    return {
        "menor": min(tamanhos),
        "maior": max(tamanhos),
        "media": round(mean(tamanhos), 1),
        "mediana": median(tamanhos),
    }


def palavras_mais_comuns(noticias, quantas=15, categoria=None):
    """Palavras que mais aparecem, no geral ou dentro de uma categoria.

    Usa os tokens já sem stopwords e ignora números e letras soltas, que
    não dizem nada sobre o assunto.
    """
    contagem = Counter()
    for noticia in noticias:
        if categoria and noticia["categoria"].strip() != categoria:
            continue
        for token in noticia["tokens_sem_vazias"]:
            if len(token) > 1 and not token[0].isdigit():
                contagem[token] += 1
    return contagem.most_common(quantas)


def conferir_qualidade(noticias):
    """Procura problemas na base: campo vazio, data estranha, repetição.

    O ideal é que dê tudo zero. Se não der, o problema está na coleta e
    precisa ser resolvido antes de usar a base para qualquer coisa.
    """
    urls = [n["url"] for n in noticias]
    chaves = [n["chave"] for n in noticias]
    return {
        "campos_vazios": {
            campo: sum(1 for n in noticias if not str(n.get(campo, "")).strip())
            for campo in CAMPOS_OBRIGATORIOS
        },
        "datas_invalidas": sum(1 for n in noticias if entender_data(n["data"]) is None),
        "urls_repetidas": len(urls) - len(set(urls)),
        "conteudos_repetidos": len(chaves) - len(set(chaves)),
    }


def escolher_amostra(noticias, quantidade=20):
    """Escolhe notícias espalhadas pelo período, para conferir na mão.

    Não é sorteio: ordena por data e pega de tantas em tantas. Assim a
    amostra é sempre a mesma e cobre a base inteira, não só o começo.
    """
    if quantidade >= len(noticias):
        return noticias
    ordenadas = sorted(noticias, key=lambda n: (n["data"], n["url"]))
    passo = (len(ordenadas) - 1) / (quantidade - 1)
    return [ordenadas[round(i * passo)] for i in range(quantidade)]


def fazer_graficos(noticias, pasta):
    """Desenha o gráfico de categorias e o de notícias por mês."""
    categorias = contar_por_categoria(noticias).most_common()
    meses = contar_por_mes(noticias)

    figura, (esquerda, direita) = plt.subplots(1, 2, figsize=(14, 5))

    nomes = [c for c, _ in categorias][::-1]
    quantidades = [q for _, q in categorias][::-1]
    esquerda.barh(nomes, quantidades, color="#2563eb")
    esquerda.set_title("Notícias por categoria")

    direita.bar(list(meses), list(meses.values()), color="#2563eb")
    direita.set_title("Notícias por mês de publicação")
    direita.tick_params(axis="x", rotation=45)

    plt.tight_layout()
    plt.savefig(pasta / "graficos.png", dpi=120)
    plt.close()


def salvar_csv(linhas, arquivo, colunas):
    """Grava uma tabela simples em CSV."""
    with open(arquivo, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(linhas)


def main():
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument("--entrada", default=ENTRADA_PADRAO)
    analise.add_argument("--pasta", default=PASTA_PADRAO)
    analise.add_argument("--amostra", type=int, default=20)
    opcoes = analise.parse_args()

    noticias = carregar(opcoes.entrada)
    pasta = Path(opcoes.pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    categorias = contar_por_categoria(noticias)
    tamanhos = estatisticas_de_tamanho(noticias)
    qualidade = conferir_qualidade(noticias)
    vocabulario = len({t for n in noticias for t in n["tokens_sem_vazias"]})

    print(f"{len(noticias)} notícias, {len(categorias)} categorias")
    print(f"palavras por notícia: menor {tamanhos['menor']}, mediana {tamanhos['mediana']}, "
          f"média {tamanhos['media']}, maior {tamanhos['maior']}")
    print(f"vocabulário: {vocabulario} palavras diferentes\n")

    print("CONFERÊNCIA DE QUALIDADE (o ideal é tudo zero)")
    print(f"  campos vazios ......... {qualidade['campos_vazios']}")
    print(f"  datas inválidas ....... {qualidade['datas_invalidas']}")
    print(f"  urls repetidas ........ {qualidade['urls_repetidas']}")
    print(f"  conteúdos repetidos ... {qualidade['conteudos_repetidos']}\n")

    print("NOTÍCIAS POR CATEGORIA")
    for categoria, quantidade in categorias.most_common():
        print(f"  {categoria:<24} {quantidade:>4}")

    print("\nPALAVRAS MAIS COMUNS EM CADA CATEGORIA")
    for categoria, _ in categorias.most_common():
        comuns = palavras_mais_comuns(noticias, 8, categoria)
        print(f"  {categoria:<24} " + ", ".join(p for p, _ in comuns))

    # Guarda tudo em arquivo, para consultar depois e colocar no relatório.
    resumo = {
        "total_de_noticias": len(noticias),
        "categorias": dict(categorias.most_common()),
        "palavras_por_noticia": tamanhos,
        "vocabulario": vocabulario,
        "qualidade": qualidade,
        "por_mes": contar_por_mes(noticias),
        "palavras_mais_comuns": palavras_mais_comuns(noticias, 30),
    }
    (pasta / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    salvar_csv(
        [{"categoria": c, "noticias": q} for c, q in categorias.most_common()],
        pasta / "categorias.csv", ["categoria", "noticias"],
    )
    salvar_csv(
        [dict(n, conferido="", observacao="") for n in escolher_amostra(noticias, opcoes.amostra)],
        pasta / "amostra_para_conferir.csv",
        ["titulo", "data", "categoria", "palavras", "url", "conferido", "observacao"],
    )
    fazer_graficos(noticias, pasta)

    print(f"\nRelatórios salvos em {pasta}/")


if __name__ == "__main__":
    main()
