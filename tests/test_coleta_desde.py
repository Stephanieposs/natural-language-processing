from datetime import date

import pandas as pd

import projeto_pln


def test_coleta_desde_para_apos_duas_paginas_antigas(monkeypatch):
    links = {
        1: ["novo-1", "novo-2"],
        2: ["novo-3", "antigo-1"],
        3: ["antigo-2"],
        4: ["antigo-3"],
    }
    dates = {
        "novo-1": "2026-11-05",
        "novo-2": "2026-10-10",
        "novo-3": "2026-09-22",
        "antigo-1": "2026-09-21",
        "antigo-2": "2026-09-20",
        "antigo-3": "2026-09-19",
    }
    visited = []
    monkeypatch.setattr(projeto_pln, "listing_url", lambda page: page)
    monkeypatch.setattr(projeto_pln, "download", lambda session, url: url)
    monkeypatch.setattr(projeto_pln, "extract_article_links", lambda page, url: links[page])
    monkeypatch.setattr(
        projeto_pln, "parse_article",
        lambda content, url: {"url": url, "published_at": dates[url]},
    )
    monkeypatch.setattr(projeto_pln, "write_jsonl", lambda records, path: visited.append(len(records)))

    collected, failed_pages, failed_articles, scanned, complete = (
        projeto_pln.collect_articles_since(date(2026, 9, 21), [], max_pages=8)
    )

    assert [item["url"] for item in collected] == ["novo-1", "novo-2", "novo-3"]
    assert (failed_pages, failed_articles, scanned, complete) == ([], 0, 4, True)
    assert visited == [2, 3, 3, 3]


def test_coleta_desde_nao_declara_cobertura_em_listagem_repetida(monkeypatch):
    monkeypatch.setattr(projeto_pln, "listing_url", lambda page: page)
    monkeypatch.setattr(projeto_pln, "download", lambda session, url: url)
    monkeypatch.setattr(projeto_pln, "extract_article_links", lambda page, url: ["mesma-url"])
    monkeypatch.setattr(
        projeto_pln, "parse_article",
        lambda content, url: {"url": url, "published_at": "2026-11-05"},
    )
    monkeypatch.setattr(projeto_pln, "write_jsonl", lambda records, path: None)

    collected, _, _, scanned, complete = projeto_pln.collect_articles_since(
        date(2026, 9, 21), [], max_pages=8,
    )

    assert len(collected) == 1
    assert scanned == 2
    assert complete is False


def test_parse_rest_article_preserva_campos_do_corpus():
    post = {
        "title": {"rendered": "Chuva &amp; vento em Blumenau"},
        "content": {"rendered": "<p>Alerta de chuva.</p><p>Vento forte.</p>"},
        "date": "2026-11-11T18:00:00",
        "link": "https://blogdojaime.com.br/chuva-vento/",
        "categories": [12],
    }

    article = projeto_pln.parse_rest_article(post, {12: "Tempo"})

    assert article["title"] == "Chuva & vento em Blumenau"
    assert article["content"] == "Alerta de chuva.\nVento forte."
    assert article["category"] == "Tempo"
    assert article["published_at"] == "2026-11-11T18:00:00"
    assert len(article["content_hash"]) == 64


def test_recorte_temporal_aceita_datas_com_e_sem_fuso():
    data = pd.DataFrame([
        {"published_at": "2026-09-21T12:00:00+00:00", "category": "Tempo", "word_count": 30, "tokens_sem_stopwords": ["chuva"]},
        {"published_at": "2026-11-11T18:00:00", "category": "Eventos", "word_count": 40, "tokens_sem_stopwords": ["evento"]},
    ])

    result = projeto_pln.create_temporal_samples(data)

    assert result["reference_date"] == "2026-11-11"
    assert result["recent_articles"] == 1
    assert result["previous_articles"] == 1


def test_meta_publica_desconta_categorias_pessoais_e_duplicatas():
    articles = [
        {"category": "Tempo", "content_hash": "a", "word_count": 50},
        {"category": "Tempo", "content_hash": "a", "word_count": 50},
        {"category": "Falecidos", "content_hash": "b", "word_count": 50},
        {"category": "Aniversários", "content_hash": "c", "word_count": 50},
        {"category": "Eventos", "content_hash": "d", "word_count": 5},
        {"category": "Eventos, Destaques", "content_hash": "e", "word_count": 50},
    ]
    assert projeto_pln.public_article_count(articles) == 2
