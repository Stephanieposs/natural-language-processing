import json

from scraper import (
    Article,
    deduplicate,
    extract_article_links,
    merge_by_url,
    parse_article,
    read_jsonl,
    write_jsonl,
)


ARTICLE_HTML = """
<article><h1 class="entry-title"> Acidente no Garcia </h1>
<time datetime="2026-08-30T10:00:00-03:00">30/08/2026</time>
<span class="cat-links"><a>Ocorrências</a></span>
<div class="entry-content"><p>Primeiro parágrafo da notícia.</p>
<script>propaganda()</script><p>Segundo parágrafo.</p></div></article>
"""

ELEMENTOR_ARTICLE_HTML = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"BlogPosting","datePublished":"2026-08-31T08:12:53-03:00","articleSection":"Tempo"}]}
</script></head><body>
<h1> Chuva volumosa continua nesta segunda-feira em Blumenau. </h1>
<div class="elementor-widget-theme-post-content"><p>31/08/2026 Primeiro parágrafo da notícia.</p>
<p>Segundo parágrafo com mais detalhes.</p></div>
</body></html>
"""


def article(title: str, content: str, url: str) -> Article:
    return Article(title, "2026-08-30", "Notícias", content, url, "2026-08-31T00:00:00+00:00")


def test_parse_article_extracts_structured_fields():
    result = parse_article(ARTICLE_HTML, "https://blogdojaime.com.br/noticia", "agora")
    assert result.title == "Acidente no Garcia"
    assert result.category == "Ocorrências"
    assert result.published_at == "2026-08-30T10:00:00-03:00"
    assert result.content == "Primeiro parágrafo da notícia.\nSegundo parágrafo."


def test_parse_article_accepts_elementor_content_and_json_ld_metadata():
    result = parse_article(ELEMENTOR_ARTICLE_HTML, "https://blogdojaime.com.br/chuva/", "agora")
    assert result.title == "Chuva volumosa continua nesta segunda-feira em Blumenau."
    assert result.category == "Tempo"
    assert result.published_at == "2026-08-31T08:12:53-03:00"
    assert result.content == "31/08/2026 Primeiro parágrafo da notícia.\nSegundo parágrafo com mais detalhes."


def test_extract_links_keeps_unique_internal_articles():
    html = """<article><h2><a href='/a/'>A</a></h2></article>
    <article><h2><a href='/a/#top'>A</a></h2></article>
    <article><h3><a href='https://outro.test/b'>B</a></h3></article>"""
    assert extract_article_links(html, "https://blogdojaime.com.br/") == ["https://blogdojaime.com.br/a/"]


def test_extract_links_accepts_current_listing_permalink_layout():
    html = """<main>
    <a href='/category/tempo/'>Tempo</a>
    <h2>Chuva volumosa continua nesta segunda-feira em Blumenau.</h2>
    <a href='/chuva-volumosa-continua-nesta-segunda-feira-em-blumenau/'>31 de agosto 2026</a>
    <a href='/noticias/'>veja mais notícias, clique aqui!</a>
    </main>"""
    assert extract_article_links(html, "https://blogdojaime.com.br/noticias/") == [
        "https://blogdojaime.com.br/chuva-volumosa-continua-nesta-segunda-feira-em-blumenau/"
    ]


def test_deduplicate_normalizes_accents_case_and_punctuation():
    items = [article("Ação", "Texto suficiente aqui", "/1"), article("ACAO!", "texto suficiente aqui.", "/2")]
    clean, duplicates, short = deduplicate(items)
    assert clean == [items[0]]
    assert duplicates == 1
    assert short == 0


def test_deduplicate_filters_short_content():
    clean, duplicates, short = deduplicate([article("Título", "curto", "/1")], minimum_words=2)
    assert clean == []
    assert duplicates == 0
    assert short == 1


def test_merge_preserves_old_articles_and_updates_known_url():
    old = article("Antiga", "conteúdo antigo", "/antiga")
    before_update = article("Título anterior", "versão anterior", "/mesma")
    updated = article("Título atualizado", "versão atual", "/mesma")
    new = article("Nova", "conteúdo novo", "/nova")

    assert merge_by_url([old, before_update], [updated, new]) == [old, updated, new]


def test_jsonl_round_trip_ignores_calculated_fields(tmp_path):
    destination = tmp_path / "noticias.jsonl"
    expected = article("Título", "conteúdo", "/noticia")
    write_jsonl([expected], destination)

    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored["content_hash"] == expected.content_hash
    assert read_jsonl(destination) == [expected]
