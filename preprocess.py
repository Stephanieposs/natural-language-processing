"""Cria representações textuais derivadas sem modificar os textos coletados."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

TOKEN_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*|\d+(?:[.,]\d+)*", re.UNICODE)
SPACE_RE = re.compile(r"\s+")

# Lista explícita e sem downloads, para manter o processamento reproduzível.
# Base: stopwords de português do NLTK (artigos, preposições, pronomes e formas
# dos verbos ser/estar/ter/haver), acrescida de contrações frequentes em textos
# jornalísticos (nesta, neste, desta, deste...). "não" está incluído como no NLTK;
# tarefas sensíveis à negação devem usar o campo `tokens`, que preserva tudo.
_NLTK_PORTUGUESE = """
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
"""
_NEWS_CONTRACTIONS = "nesta neste nestas nestes nessa nesse nessas nesses desta deste destas destes dessa desse dessas desses naquela naquele daquela daquele nums numas"
PORTUGUESE_STOPWORDS = frozenset(f"{_NLTK_PORTUGUESE} {_NEWS_CONTRACTIONS}".split())


def normalize_text(value: str, lowercase: bool = True) -> str:
    """Normaliza Unicode e espaços, preservando acentos e conteúdo semântico."""
    value = unicodedata.normalize("NFC", value or "")
    value = SPACE_RE.sub(" ", value).strip()
    return value.lower() if lowercase else value


def tokenize(value: str) -> list[str]:
    """Separa palavras e números, preservando palavras com acentos e hífen."""
    return TOKEN_RE.findall(value)


def preprocess_record(record: dict, remove_stopwords: bool = True) -> dict:
    """Acrescenta campos derivados a uma cópia do registro original."""
    result = dict(record)
    title = normalize_text(str(record.get("title", "")))
    content = normalize_text(str(record.get("content", "")))
    text = normalize_text(f"{title} {content}")
    tokens = tokenize(text)
    filtered = [token for token in tokens if token not in PORTUGUESE_STOPWORDS]
    result.update(
        {
            "text_normalized": text,
            "tokens": tokens,
            "tokens_without_stopwords": filtered if remove_stopwords else tokens,
            "text_for_model": " ".join(filtered if remove_stopwords else tokens),
        }
    )
    return result


def preprocess_file(source: Path, destination: Path, remove_stopwords: bool = True) -> int:
    """Processa um JSONL de forma atômica e retorna o número de registros."""
    if not source.exists():
        raise FileNotFoundError(f"Base processada não encontrada: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    count = 0
    try:
        with source.open(encoding="utf-8") as input_stream, temporary.open("w", encoding="utf-8") as output_stream:
            for line_number, line in enumerate(input_stream, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"JSON inválido em {source}:{line_number}") from error
                if not isinstance(record, dict):
                    raise ValueError(f"Registro não é um objeto em {source}:{line_number}")
                output_stream.write(json.dumps(preprocess_record(record, remove_stopwords), ensure_ascii=False) + "\n")
                count += 1
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/noticias.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/noticias_nlp.jsonl"))
    parser.add_argument(
        "--keep-stopwords",
        action="store_true",
        help="Mantém stopwords em tokens_without_stopwords e text_for_model",
    )
    args = parser.parse_args()
    count = preprocess_file(args.input, args.output, remove_stopwords=not args.keep_stopwords)
    print(f"{count} notícias processadas em {args.output}")


if __name__ == "__main__":
    main()
