"""Consolida arquivos brutos parciais (coletas paralelas) em uma única base."""

from __future__ import annotations

import argparse
import csv
import logging
from collections import Counter
from pathlib import Path
from typing import Iterable

from scraper import Article, deduplicate, merge_by_url, read_jsonl, write_csv, write_jsonl


def provenance_rows(sources: Iterable[Path]) -> list[dict[str, str | int]]:
    """Cruza a listagem de origem (nome do arquivo parcial) com a categoria declarada pelo portal."""
    rows: list[dict[str, str | int]] = []
    for source in sources:
        declared = Counter((article.category.strip() or "Sem categoria") for article in read_jsonl(source))
        rows.extend(
            {"listing": source.stem, "declared_category": category, "count": count}
            for category, count in declared.most_common()
        )
    return rows


def write_provenance(sources: Iterable[Path], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("listing", "declared_category", "count"))
        writer.writeheader()
        writer.writerows(provenance_rows(sources))


def merge_files(
    sources: Iterable[Path],
    raw_destination: Path,
    processed_destination: Path,
    minimum_words: int = 20,
) -> tuple[list[Article], list[Article], int, int]:
    """Une o histórico existente e os arquivos parciais por URL e recalcula a base processada.

    O histórico já gravado em ``raw_destination`` é lido primeiro; cada arquivo em
    ``sources`` acrescenta URLs novas e atualiza URLs conhecidas, na ordem informada.
    Retorna (histórico consolidado, base limpa, duplicadas por hash, textos curtos).
    """
    merged = read_jsonl(raw_destination)
    for source in sources:
        partial = read_jsonl(source)
        logging.info("Lendo %s: %d registros", source, len(partial))
        merged = merge_by_url(merged, partial)
    write_jsonl(merged, raw_destination)
    clean, duplicates, short = deduplicate(merged, minimum_words)
    write_jsonl(clean, processed_destination)
    write_csv(clean, processed_destination.with_suffix(".csv"))
    return merged, clean, duplicates, short


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path, help="Arquivos JSONL brutos parciais")
    parser.add_argument("--raw", type=Path, default=Path("data/raw/noticias.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/noticias.jsonl"))
    parser.add_argument("--minimum-words", type=int, default=20)
    parser.add_argument(
        "--provenance",
        type=Path,
        default=Path("reports/listing_vs_category.csv"),
        help="CSV cruzando listagem de origem e categoria declarada (vazio para não gerar)",
    )
    args = parser.parse_args()
    if args.minimum_words < 0:
        parser.error("minimum-words não pode ser negativo")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    merged, clean, duplicates, short = merge_files(args.sources, args.raw, args.output, args.minimum_words)
    if str(args.provenance):
        write_provenance(args.sources, args.provenance)
        logging.info("Proveniência gravada em %s", args.provenance)
    logging.info(
        "Consolidado: %d no histórico bruto, %d únicas, %d duplicadas e %d curtas. Bruto: %s; processado: %s",
        len(merged), len(clean), duplicates, short, args.raw, args.output,
    )


if __name__ == "__main__":
    main()
