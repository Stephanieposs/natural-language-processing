"""Baixa notícias do Blog do Jaime e salva em dados/noticias_coletadas.jsonl.

Uso:
    python coletar.py                      # 3 páginas de cada categoria
    python coletar.py --paginas 10         # coleta mais fundo
    python coletar.py --categorias tempo eventos
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SITE = "https://blogdojaime.com.br"

# As seções do portal. A listagem geral (/noticias/) só tem 2 páginas,
# então coletamos por categoria para conseguir profundidade e variedade.
CATEGORIAS = [
    "noticias", "ocorrencias", "transito", "tempo", "eventos", "destaques",
    "diversos", "saude", "esportes", "falecidos", "aniversarios",
]

# O portal responde 403 se o User-Agent não parecer um navegador de verdade.
CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

ARQUIVO_PADRAO = Path("dados/noticias_coletadas.jsonl")


def limpar_espacos(texto):
    """Troca quebras de linha e espaços repetidos por um espaço só."""
    return " ".join(texto.split())


def baixar_pagina(url, espera=1.5):
    """Baixa o HTML de uma página e espera um pouco antes da próxima.

    A espera não é opcional: as páginas de arquivo do portal são lentas e
    uma coleta apressada chega a derrubá-las.
    """
    resposta = requests.get(url, headers=CABECALHOS, timeout=30)
    resposta.raise_for_status()
    time.sleep(espera)
    return resposta.text


def ler_json_ld(sopa, chave):
    """Procura um campo nos blocos JSON-LD que o WordPress publica na página.

    É de lá que vêm a data e a categoria confiáveis, já que o texto visível
    aparece em formatos diferentes ("31 de agosto", "31/08/2026").
    """
    for script in sopa.find_all("script", type="application/ld+json"):
        try:
            dados = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue

        # O WordPress costuma agrupar tudo dentro de "@graph".
        if isinstance(dados, dict) and "@graph" in dados:
            blocos = dados["@graph"]
        elif isinstance(dados, list):
            blocos = dados
        else:
            blocos = [dados]

        for bloco in blocos:
            if not isinstance(bloco, dict):
                continue
            valor = bloco.get(chave)
            if isinstance(valor, list) and valor:
                valor = valor[0]
            if valor:
                return limpar_espacos(str(valor))
    return ""


def extrair_noticia(html, url):
    """Monta o dicionário de uma notícia a partir do HTML da página."""
    sopa = BeautifulSoup(html, "html.parser")

    titulo = sopa.find("h1")
    titulo = limpar_espacos(titulo.get_text(" ", strip=True)) if titulo else ""

    # O portal usa o tema Elementor, que guarda o texto em um container próprio.
    # Os outros seletores são reserva, para posts em formato antigo.
    corpo = None
    for seletor in (".elementor-widget-theme-post-content", ".entry-content",
                    ".post-content", "article"):
        corpo = sopa.select_one(seletor)
        if corpo:
            break

    texto = ""
    if corpo:
        # Fora tudo que não é notícia: scripts, menus, botões de compartilhar.
        for lixo in corpo.select("script, style, nav, form, iframe, .social-share"):
            lixo.decompose()
        # O separador " " evita colar palavras quando há <br> dentro do parágrafo.
        paragrafos = [limpar_espacos(p.get_text(" ", strip=True)) for p in corpo.find_all("p")]
        texto = "\n".join(p for p in paragrafos if p)

    return {
        "titulo": titulo,
        "data": ler_json_ld(sopa, "datePublished"),
        "categoria": ler_json_ld(sopa, "articleSection"),
        "texto": texto,
        "url": url,
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
    }


def eh_link_de_noticia(link):
    """Diz se um link é de notícia, e não de menu, categoria ou imagem.

    No portal, o endereço de uma notícia tem um único trecho depois do domínio:
    /titulo-da-noticia/. Categorias e paginação têm mais de um.
    """
    endereco = urlparse(link)
    if endereco.netloc.replace("www.", "") != "blogdojaime.com.br":
        return False

    caminho = endereco.path.strip("/")
    if not caminho or "/" in caminho:
        return False
    if caminho in ("noticias", "contato", "anuncie-conosco"):
        return False
    if caminho.startswith(("category", "tag", "author", "page", "wp-")):
        return False
    return not caminho.endswith((".jpg", ".jpeg", ".png", ".webp", ".pdf"))


def procurar_links(html, url_da_pagina):
    """Devolve os links de notícia encontrados em uma página de listagem."""
    sopa = BeautifulSoup(html, "html.parser")
    links = []
    for tag in sopa.find_all("a", href=True):
        link = urljoin(url_da_pagina, tag["href"]).split("#")[0].rstrip("/") + "/"
        if eh_link_de_noticia(link) and link not in links:
            links.append(link)
    return links


def coletar_categoria(categoria, paginas, ja_coletadas, espera):
    """Percorre as páginas de uma categoria e devolve as notícias novas."""
    noticias = []
    for numero in range(1, paginas + 1):
        endereco = f"{SITE}/category/{categoria}/"
        if numero > 1:
            endereco += f"page/{numero}/"

        try:
            links = procurar_links(baixar_pagina(endereco, espera), endereco)
        except requests.RequestException as erro:
            print(f"    página {numero} não abriu: {erro}")
            continue

        for link in links:
            if link in ja_coletadas:
                continue  # já temos essa notícia de uma execução anterior
            try:
                noticia = extrair_noticia(baixar_pagina(link, espera), link)
            except requests.RequestException as erro:
                print(f"    {link} falhou: {erro}")
                continue
            if noticia["titulo"]:
                noticias.append(noticia)
                ja_coletadas.add(link)
    return noticias


def carregar(arquivo):
    """Lê as notícias já salvas. Devolve lista vazia se o arquivo não existe."""
    if not Path(arquivo).exists():
        return []
    with open(arquivo, encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def salvar(noticias, arquivo):
    """Grava a lista de notícias, uma por linha, no formato JSONL."""
    Path(arquivo).parent.mkdir(parents=True, exist_ok=True)
    with open(arquivo, "w", encoding="utf-8") as f:
        for noticia in noticias:
            f.write(json.dumps(noticia, ensure_ascii=False) + "\n")


def main():
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument("--paginas", type=int, default=3, help="páginas por categoria")
    analise.add_argument("--categorias", nargs="+", default=CATEGORIAS)
    analise.add_argument("--espera", type=float, default=1.5, help="segundos entre requisições")
    analise.add_argument("--arquivo", default=ARQUIVO_PADRAO)
    opcoes = analise.parse_args()

    # A coleta é incremental: o que já foi baixado antes não é baixado de novo.
    noticias = carregar(opcoes.arquivo)
    ja_coletadas = {n["url"] for n in noticias}
    print(f"{len(noticias)} notícias já estavam salvas.\n")

    for categoria in opcoes.categorias:
        print(f"[{categoria}] lendo {opcoes.paginas} página(s)...")
        novas = coletar_categoria(categoria, opcoes.paginas, ja_coletadas, opcoes.espera)
        noticias.extend(novas)
        print(f"    {len(novas)} notícias novas")
        salvar(noticias, opcoes.arquivo)  # salva a cada categoria, para não perder tudo

    print(f"\nTotal: {len(noticias)} notícias em {opcoes.arquivo}")


if __name__ == "__main__":
    main()
