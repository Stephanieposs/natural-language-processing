"""Gera a análise exploratória e uma amostra para revisão da base de notícias."""

from __future__ import annotations

import argparse
import csv
import html
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

from preprocess import PORTUGUESE_STOPWORDS, normalize_text, tokenize

REQUIRED_FIELDS = ("title", "published_at", "category", "content", "url")


def load_records(source: Path) -> list[dict]:
    records = []
    if not source.exists():
        return records
    with source.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"JSON inválido em {source}:{number}") from error
            if not isinstance(record, dict):
                raise ValueError(f"Registro não é um objeto em {source}:{number}")
            records.append(record)
    return records


def parse_date(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d de %B de %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def describe(records: list[dict], minimum_words: int) -> dict:
    word_counts = [int(r.get("word_count") or len(str(r.get("content", "")).split())) for r in records]
    dates = [parsed for r in records if (parsed := parse_date(str(r.get("published_at", ""))))]
    categories = Counter((str(r.get("category", "")).strip() or "Sem categoria") for r in records)
    missing = {field: sum(not str(r.get(field, "")).strip() for r in records) for field in REQUIRED_FIELDS}
    urls = [str(r.get("url", "")).strip() for r in records if str(r.get("url", "")).strip()]
    hashes = [str(r.get("content_hash", "")).strip() for r in records if str(r.get("content_hash", "")).strip()]
    return {
        "total_articles": len(records),
        "unique_urls": len(set(urls)),
        "duplicate_urls": len(urls) - len(set(urls)),
        "duplicate_content_hashes": len(hashes) - len(set(hashes)),
        "short_articles": sum(count < minimum_words for count in word_counts),
        "minimum_words": minimum_words,
        "missing_fields": missing,
        "invalid_dates": sum(bool(str(r.get("published_at", "")).strip()) and parse_date(str(r["published_at"])) is None for r in records),
        "oldest_publication": min(dates).date().isoformat() if dates else None,
        "newest_publication": max(dates).date().isoformat() if dates else None,
        "word_count": {
            "minimum": min(word_counts) if word_counts else 0,
            "maximum": max(word_counts) if word_counts else 0,
            "mean": round(statistics.fmean(word_counts), 2) if word_counts else 0,
            "median": statistics.median(word_counts) if word_counts else 0,
        },
        "categories": dict(categories.most_common()),
    }


def content_tokens(record: dict) -> list[str]:
    """Tokens de título + conteúdo, minúsculos, sem stopwords e sem números."""
    text = normalize_text(f"{record.get('title', '')} {record.get('content', '')}")
    return [t for t in tokenize(text) if t not in PORTUGUESE_STOPWORDS and not t[0].isdigit() and len(t) > 1]


def top_terms(records: list[dict], size: int = 30) -> dict[str, list[tuple[str, int]]]:
    """Termos mais frequentes no geral e por categoria; a chave "geral" vem primeiro."""
    overall: Counter = Counter()
    by_category: dict[str, Counter] = {}
    for record in records:
        tokens = content_tokens(record)
        overall.update(tokens)
        category = str(record.get("category", "")).strip() or "Sem categoria"
        by_category.setdefault(category, Counter()).update(tokens)
    result = {"geral": overall.most_common(size)}
    for category, counter in sorted(by_category.items(), key=lambda item: -sum(item[1].values())):
        result[category] = counter.most_common(size)
    return result


def vocabulary_size(records: list[dict]) -> int:
    return len({token for record in records for token in content_tokens(record)})


def write_csv(rows: Iterable[dict], destination: Path, fields: tuple[str, ...]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def select_sample(records: list[dict], size: int) -> list[dict]:
    """Seleciona uma amostra reproduzível e espalhada por toda a base."""
    if size <= 0 or not records:
        return []
    ordered = sorted(records, key=lambda r: (str(r.get("published_at", "")), str(r.get("url", ""))))
    if size >= len(ordered):
        return ordered
    indexes = {round(i * (len(ordered) - 1) / (size - 1)) for i in range(size)} if size > 1 else {0}
    return [ordered[index] for index in sorted(indexes)]


def write_svg_bars(values: dict[str, int], destination: Path, title: str) -> None:
    """Cria um gráfico SVG sem exigir bibliotecas gráficas externas."""
    items = list(values.items())[:15]
    width, row_height = 900, 34
    height = 80 + row_height * max(1, len(items))
    maximum = max((value for _, value in items), default=1)
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<style>text{font-family:Arial,sans-serif;font-size:14px}.title{font-size:20px;font-weight:bold}</style>',
        f'<text class="title" x="20" y="30">{html.escape(title)}</text>',
    ]
    if not items:
        elements.append('<text x="20" y="70">Nenhum dado disponível</text>')
    for index, (label, value) in enumerate(items):
        y = 60 + index * row_height
        bar_width = int(580 * value / maximum)
        elements.extend((
            f'<text x="20" y="{y + 18}">{html.escape(str(label)[:32])}</text>',
            f'<rect x="270" y="{y}" width="{bar_width}" height="22" fill="#2563eb"/>',
            f'<text x="{280 + bar_width}" y="{y + 17}">{value}</text>',
        ))
    elements.append("</svg>")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(elements), encoding="utf-8")


def generate(
    raw_source: Path, processed_source: Path, output: Path, minimum_words: int, sample_size: int, top_size: int = 30
) -> dict:
    raw = load_records(raw_source)
    processed = load_records(processed_source)
    raw_summary = describe(raw, minimum_words)
    processed_summary = describe(processed, minimum_words)
    processed_summary["vocabulary_size"] = vocabulary_size(processed)
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "raw": raw_summary,
        "processed": processed_summary,
        "removed_during_processing": len(raw) - len(processed),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(
        ({"category": category, "count": count} for category, count in processed_summary["categories"].items()),
        output / "category_distribution.csv", ("category", "count"),
    )
    months = Counter(
        parsed.strftime("%Y-%m")
        for record in processed
        if (parsed := parse_date(str(record.get("published_at", ""))))
    )
    write_csv(({"month": month, "count": months[month]} for month in sorted(months)), output / "news_by_month.csv", ("month", "count"))
    issues = []
    for record in raw:
        missing = ", ".join(field for field in REQUIRED_FIELDS if not str(record.get(field, "")).strip())
        words = int(record.get("word_count") or len(str(record.get("content", "")).split()))
        if missing or words < minimum_words:
            issues.append({"url": record.get("url", ""), "missing_fields": missing, "word_count": words})
    write_csv(issues, output / "quality_issues.csv", ("url", "missing_fields", "word_count"))
    sample = [
        {
            "title": r.get("title", ""), "published_at": r.get("published_at", ""),
            "category": r.get("category", ""), "word_count": r.get("word_count", ""),
            "url": r.get("url", ""), "review_status": "", "review_notes": "",
        }
        for r in select_sample(processed, sample_size)
    ]
    write_csv(sample, output / "review_sample.csv", ("title", "published_at", "category", "word_count", "url", "review_status", "review_notes"))
    write_csv(
        (
            {"scope": scope, "rank": rank, "term": term, "count": count}
            for scope, terms in top_terms(processed, top_size).items()
            for rank, (term, count) in enumerate(terms, 1)
        ),
        output / "top_terms.csv", ("scope", "rank", "term", "count"),
    )
    write_svg_bars(processed_summary["categories"], output / "figures/categories.svg", "Notícias por categoria")
    write_svg_bars(dict(sorted(months.items())), output / "figures/news_by_month.svg", "Notícias por mês")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/noticias.jsonl"))
    parser.add_argument("--processed", type=Path, default=Path("data/processed/noticias.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("reports"))
    parser.add_argument("--minimum-words", type=int, default=20)
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--top-terms", type=int, default=30, help="Termos mais frequentes por categoria")
    args = parser.parse_args()
    if args.minimum_words < 0 or args.sample_size < 0 or args.top_terms < 0:
        parser.error("minimum-words, sample-size e top-terms não podem ser negativos")
    summary = generate(args.raw, args.processed, args.output, args.minimum_words, args.sample_size, args.top_terms)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
