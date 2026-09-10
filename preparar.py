"""Limpa as notícias coletadas e prepara o texto para tarefas de PLN.

Uso:
    python preparar.py
    python preparar.py --minimo-palavras 30
"""

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import simplemma
from nltk.stem import SnowballStemmer

ENTRADA_PADRAO = Path("dados/noticias_coletadas.jsonl")
SAIDA_PADRAO = Path("dados/noticias_preparadas.jsonl")

# Palavras muito comuns que não ajudam a identificar o assunto do texto.
# É a lista do NLTK para português, escrita aqui para o programa rodar sem
# precisar baixar nada. Repare que "não" está na lista: isso atrapalha quem
# for analisar negação, e por isso guardamos também os tokens sem filtro.
PALAVRAS_VAZIAS = frozenset("""
a à ao aos aquela aquelas aquele aqueles aquilo as às até com como da das de dela delas
dele deles depois do dos e é ela elas ele eles em entre era eram éramos essa essas esse
esses esta está estamos estão estar estas estava estavam estávamos este esteja estejam
estejamos estes esteve estive estivemos estiver estivera estiveram estivéramos estiverem
estivermos estivesse estivessem estivéssemos estou eu foi fomos for fora foram fôramos
forem formos fosse fossem fôssemos fui há haja hajam hajamos hão havemos haver hei houve
houvemos houver houvera houverá houveram houvéramos houverão houverei houverem houveremos
houveria houveriam houveríamos houvermos houvesse houvessem houvéssemos isso isto já lhe
lhes mais mas me mesmo meu meus minha minhas muito na não nas nem no nos nós nossa nossas
nosso nossos num numa o os ou para pela pelas pelo pelos por qual quando que quem são se
seja sejam sejamos sem ser será serão serei seremos seria seriam seríamos seu seus só
somos sou sua suas também te tem tém temos tenha tenham tenhamos tenho terá terão terei
teremos teria teriam teríamos teu teus teve tinha tinham tínhamos tive tivemos tiver
tivera tiveram tivéramos tiverem tivermos tivesse tivessem tivéssemos tu tua tuas um uma
você vocês vos
nesta neste nestas nestes nessa nesse nessas nesses desta deste destas destes dessa desse
dessas desses naquela naquele daquela daquele nums numas
""".split())

# Linha que começa com um desses rótulos é crédito do portal, não notícia.
# Descobrimos isso olhando a base: das 455 linhas que começavam com "Fonte:",
# 454 estavam nas duas últimas linhas do texto.
CREDITO_NO_INICIO = re.compile(r"^\s*(fonte|foto|imagem|crédito|credito|oferecimento)s?\s*:", re.I)

# Às vezes o crédito vem grudado no fim de uma frase de verdade.
CREDITO_NO_FIM = re.compile(r"\s*\b(fonte|crédito|credito|oferecimento)s?\s*:.*$", re.I)

# Chamadas do próprio blog, que aparecem no meio das notícias.
PROPAGANDA = re.compile(r"mande um whatsapp para o jaime|foto meramente ilustrativa|#blogdojaime", re.I)

# Aceita palavras (com acento, hífen e apóstrofo) e números (com vírgula ou ponto).
# A pontuação some sozinha, por não se encaixar em nenhum dos dois casos.
PALAVRAS_E_NUMEROS = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*|\d+(?:[.,]\d+)*", re.UNICODE)

radicalizador = SnowballStemmer("portuguese")


def limpar_creditos(texto):
    """Tira os créditos de fonte e foto e as chamadas do blog."""
    linhas_boas = []
    for linha in (texto or "").split("\n"):
        if PROPAGANDA.search(linha) or CREDITO_NO_INICIO.match(linha):
            continue
        linha = CREDITO_NO_FIM.sub("", linha).strip()
        if linha:
            linhas_boas.append(linha)
    return "\n".join(linhas_boas)


def normalizar(texto):
    """Deixa o texto em minúsculas, com espaços arrumados e acentos preservados.

    Tirar acento juntaria palavras diferentes, então isso NÃO é feito aqui.
    """
    texto = unicodedata.normalize("NFC", texto or "")
    return " ".join(texto.split()).lower()


def tokenizar(texto):
    """Separa o texto em palavras e números, jogando fora a pontuação."""
    return PALAVRAS_E_NUMEROS.findall(texto)


def tirar_palavras_vazias(tokens):
    """Remove as palavras da lista de stopwords."""
    return [t for t in tokens if t not in PALAVRAS_VAZIAS]


def achar_radicais(tokens):
    """Corta os sufixos e deixa só o radical: 'notícias' vira 'notíc'.

    Usamos o Snowball porque ele já vem com o NLTK. O RSLP seria melhor para
    português, mas exige baixar um arquivo extra.
    """
    return [radicalizador.stem(t) for t in tokens]


def achar_lemas(tokens):
    """Devolve a palavra do dicionário: 'chuvas' vira 'chuva', 'foram' vira 'ser'."""
    return [simplemma.lemmatize(t, lang="pt") for t in tokens]


def gerar_chave(titulo, texto):
    """Cria uma identificação do conteúdo, para descobrir notícias repetidas.

    Tira acento, pontuação e maiúsculas de propósito, para que "Ação" e "ACAO!"
    gerem a mesma chave. O portal republica a mesma nota em dias seguidos,
    trocando só o endereço, e é assim que percebemos.
    """
    junto = f"{titulo} {texto}"
    sem_acento = unicodedata.normalize("NFKD", junto).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()
    return hashlib.sha256(limpo.encode("utf-8")).hexdigest()


def preparar_noticia(noticia):
    """Acrescenta os campos de PLN sem mexer no que veio do site."""
    preparada = dict(noticia)

    texto_limpo = limpar_creditos(noticia.get("texto", ""))
    texto = normalizar(f"{noticia.get('titulo', '')} {texto_limpo}")

    tokens = tokenizar(texto)
    sem_vazias = tirar_palavras_vazias(tokens)
    radicais = achar_radicais(sem_vazias)
    lemas = achar_lemas(sem_vazias)

    preparada.update({
        "texto_limpo": texto_limpo,
        "texto_normalizado": texto,
        "palavras": len(texto_limpo.split()),
        "chave": gerar_chave(noticia.get("titulo", ""), noticia.get("texto", "")),
        "tokens": tokens,
        "tokens_sem_vazias": sem_vazias,
        "texto_para_modelo": " ".join(sem_vazias),
        "radicais": radicais,
        "lemas": lemas,
        "texto_radicais": " ".join(radicais),
        "texto_lemas": " ".join(lemas),
    })
    return preparada


def tirar_repetidas_e_curtas(noticias, minimo_palavras):
    """Fica só com as notícias novas e com texto de tamanho razoável.

    Devolve a lista boa e quantas foram descartadas de cada tipo, para
    conseguirmos contar isso no relatório.
    """
    boas = []
    chaves_vistas = set()
    repetidas = curtas = 0

    for noticia in noticias:
        if noticia["palavras"] < minimo_palavras:
            curtas += 1
        elif noticia["chave"] in chaves_vistas:
            repetidas += 1
        else:
            chaves_vistas.add(noticia["chave"])
            boas.append(noticia)

    return boas, repetidas, curtas


def salvar_jsonl(noticias, arquivo):
    """Grava uma notícia por linha."""
    Path(arquivo).parent.mkdir(parents=True, exist_ok=True)
    with open(arquivo, "w", encoding="utf-8") as f:
        for noticia in noticias:
            f.write(json.dumps(noticia, ensure_ascii=False) + "\n")


def salvar_csv(noticias, arquivo):
    """Grava uma versão em tabela, sem as listas de tokens, para abrir no Excel."""
    colunas = ["titulo", "data", "categoria", "texto", "url", "palavras", "chave"]
    with open(arquivo, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(noticias)


def main():
    analise = argparse.ArgumentParser(description=__doc__)
    analise.add_argument("--entrada", default=ENTRADA_PADRAO)
    analise.add_argument("--saida", default=SAIDA_PADRAO)
    analise.add_argument("--minimo-palavras", type=int, default=20)
    opcoes = analise.parse_args()

    with open(opcoes.entrada, encoding="utf-8") as f:
        coletadas = [json.loads(linha) for linha in f if linha.strip()]
    print(f"{len(coletadas)} notícias coletadas.")

    preparadas = [preparar_noticia(n) for n in coletadas]
    boas, repetidas, curtas = tirar_repetidas_e_curtas(preparadas, opcoes.minimo_palavras)

    salvar_jsonl(boas, opcoes.saida)
    salvar_csv(boas, str(opcoes.saida).replace(".jsonl", ".csv"))

    com_credito = sum(1 for n in boas if n["texto_limpo"] != n["texto"])
    print(f"{repetidas} repetidas e {curtas} curtas foram descartadas.")
    print(f"{com_credito} notícias tinham crédito ou propaganda no meio do texto.")
    print(f"\n{len(boas)} notícias prontas em {opcoes.saida}")


if __name__ == "__main__":
    main()
