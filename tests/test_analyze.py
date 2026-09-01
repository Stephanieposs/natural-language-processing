import csv
import json

from analyze import describe, generate, parse_date, select_sample


def record(index, category="Notícias", words=3):
    return {
        "title": f"Notícia {index}", "published_at": f"2026-08-{index:02d}",
        "category": category, "content": "palavra " * words,
        "url": f"https://example.test/{index}", "content_hash": str(index),
        "word_count": words,
    }


def test_describe_reports_quality_and_distribution():
    records = [record(1, "Eventos", 10), record(2, "Eventos", 2), record(3, "Saúde", 5)]
    summary = describe(records, minimum_words=5)
    assert summary["total_articles"] == 3
    assert summary["short_articles"] == 1
    assert summary["categories"] == {"Eventos": 2, "Saúde": 1}
    assert summary["word_count"]["median"] == 5


def test_parse_date_accepts_iso_and_rejects_invalid():
    assert parse_date("2026-08-31T10:00:00-03:00").date().isoformat() == "2026-08-31"
    assert parse_date("data desconhecida") is None


def test_sample_is_reproducible_and_spread():
    records = [record(i) for i in range(1, 11)]
    assert [r["title"] for r in select_sample(records, 3)] == ["Notícia 1", "Notícia 5", "Notícia 10"]


def test_generate_writes_all_report_artifacts(tmp_path):
    raw = tmp_path / "raw.jsonl"
    processed = tmp_path / "processed.jsonl"
    output = tmp_path / "reports"
    rows = [record(1, "Eventos", 10), record(2, "Saúde", 2)]
    raw.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    processed.write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")

    summary = generate(raw, processed, output, minimum_words=5, sample_size=1)

    assert summary["removed_during_processing"] == 1
    assert {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()} == {
        "summary.json", "category_distribution.csv", "news_by_month.csv",
        "quality_issues.csv", "review_sample.csv", "figures/categories.svg",
        "figures/news_by_month.svg",
    }
    with (output / "review_sample.csv").open(encoding="utf-8") as stream:
        assert list(csv.DictReader(stream))[0]["review_status"] == ""
