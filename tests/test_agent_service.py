import json
import threading
import time
from datetime import datetime
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import agent_service as agent
import pytest
import requests
from web_server import Handler


def test_recorte_e_noticias_ja_vistas(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "DATA", tmp_path)
    documents = [
        {"id": 0, "title": "Chuva em Blumenau", "date": "2026-11-16", "category": "Tempo", "url": "https://example.com/chuva-hoje"},
        {"id": 1, "title": "Exposicao", "date": "2026-11-16", "category": "Eventos", "url": "https://example.com/arte"},
        {"id": 2, "title": "Chuva ontem", "date": "2026-11-15", "category": "Tempo", "url": "https://example.com/chuva-ontem"},
    ]
    (tmp_path / "catalog.json").write_text(json.dumps({"documents": documents, "snapshot_date": "2026-11-16", "stopwords": []}), encoding="utf-8")
    (tmp_path / "tfidf.json").write_text(json.dumps([["chuva", 1.5, [[0, 0.4], [2, 0.4]]]]), encoding="utf-8")
    (tmp_path / "word2vec.json").write_text(json.dumps({"word_vectors": {"chuva": [1, 0]}, "document_vectors": [[1, 0], [0, 1], [1, 0]]}), encoding="utf-8")

    daily = agent.select_articles("chuva", "daily")
    assert [item["id"] for item in daily["articles"]] == [0]
    weekly = agent.select_articles("chuva", "weekly", seen_urls=[documents[0]["url"]])
    assert [item["id"] for item in weekly["articles"]] == [2]


def test_evento_nao_seleciona_mencao_lateral(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "DATA", tmp_path)
    documents = [
        {"id": 0, "title": "Natal no Parque Vila Germânica", "date": "2026-11-16", "category": "Eventos", "url": "https://example.com/natal"},
        {"id": 1, "title": "Programação da Oktoberfest", "date": "2026-11-15", "category": "Oktoberfest", "url": "https://example.com/festa"},
    ]
    (tmp_path / "catalog.json").write_text(json.dumps({"documents": documents, "snapshot_date": "2026-11-16", "stopwords": []}), encoding="utf-8")
    (tmp_path / "tfidf.json").write_text(json.dumps([["oktoberfest", 1.0, [[0, 0.7], [1, 0.7]]]]), encoding="utf-8")
    (tmp_path / "word2vec.json").write_text(json.dumps({"word_vectors": {"oktoberfest": [1, 0]}, "document_vectors": [[1, 0], [1, 0]]}), encoding="utf-8")
    # A busca do evento só conserva notícias realmente identificadas como tal.
    assert [item["id"] for item in agent.select_articles("Oktoberfest", "weekly")["articles"]] == [1]


def test_gemini_recebe_apenas_fontes_e_devolve_links(monkeypatch):
    calls = {}
    attempts = []
    delays = []

    def fake_post(url, **kwargs):
        attempts.append(url)
        calls.update(kwargs)
        assert url == "https://generativelanguage.googleapis.com/v1beta/interactions"
        if len(attempts) < 3:
            return SimpleNamespace(status_code=503, ok=False)
        output = {"resumo": "Houve chuva na cidade.", "destaques": [
            {"titulo": "Chuva em Blumenau", "texto": "A notícia informa chuva na cidade.", "fontes": [1]}],
            "observacao": "Confira a fonte original."}
        return SimpleNamespace(status_code=200, ok=True, json=lambda: {"steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(output)}]}]})

    monkeypatch.setattr(agent.requests, "post", fake_post)
    monkeypatch.setattr(agent.time, "sleep", delays.append)
    monkeypatch.setattr(agent, "settings", lambda: {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.8-flash"})
    article = {"title": "Chuva em Blumenau", "date": "2026-11-16", "category": "Tempo", "url": "https://example.com/chuva"}
    report = agent.generate_report("chuva", {"articles": [article], "start": "2026-11-16", "end": "2026-11-16"})
    assert calls["json"]["store"] is False
    assert calls["json"]["model"] == "gemini-3.8-flash"
    assert "https://example.com/chuva" in calls["json"]["input"]
    assert calls["json"]["response_format"]["mime_type"] == "application/json"
    assert "Houve chuva" in agent.render_report_text(report)
    assert "https://example.com/chuva" in agent.render_report_html(report)
    assert report["highlights"][0]["sources"] == [1]
    assert len(attempts) == 3
    assert delays == [1, 2]


def test_gemini_indisponivel_falha_sem_envio(monkeypatch):
    monkeypatch.setattr(agent, "settings", lambda: {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-3.1-flash-lite"})
    monkeypatch.setattr(agent.requests, "post", lambda *args, **kwargs: SimpleNamespace(status_code=503, ok=False))
    monkeypatch.setattr(agent.time, "sleep", lambda _: None)
    selection = {"articles": [{"title": "Chuva", "date": "2026-11-16", "category": "Tempo", "url": "https://example.com/chuva"}], "start": "2026-11-16", "end": "2026-11-16"}
    with pytest.raises(RuntimeError, match="temporariamente sobrecarregado"):
        agent.generate_report("chuva", selection)


def test_envio_de_previa_so_uma_vez(monkeypatch):
    sent = []
    monkeypatch.setattr(agent, "send_email", lambda *args: sent.append(args))
    token = "token-teste"
    agent.PREVIEWS[token] = (datetime.now(), "Relatorio de teste", "chuva")
    assert agent.send_preview({"token": token, "email": "pessoa@example.com"})["sent"] is True
    assert sent == [("pessoa@example.com", "Relatorio de teste", "chuva")]
    assert token not in agent.PREVIEWS


def test_smtp_proprio_usa_tls_e_conta_configurada(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["To"], message["From"], message))

    monkeypatch.setattr(agent.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(agent, "settings", lambda: {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_USER": "usuario", "SMTP_PASSWORD": "segredo-teste", "SMTP_FROM": "remetente@example.com"})
    report = {"area": "chuva", "start": "2026-11-16", "end": "2026-11-16",
              "summary": "Chuva na cidade.", "highlights": [{"title": "Previsão", "text": "Há chuva.", "sources": [1]}],
              "closing": "Confira as fontes.", "articles": [{"title": "Chuva em Blumenau", "date": "2026-11-16",
              "category": "Tempo", "url": "https://example.com/chuva"}]}
    agent.send_email("pessoa@example.com", report, "chuva")
    assert calls[0][:3] == ("connect", "smtp.example.com", 587)
    assert calls[1] == ("starttls",)
    assert calls[2][:2] == ("login", "usuario")
    assert calls[3][1:3] == ("pessoa@example.com", "remetente@example.com")
    message = calls[3][3]
    assert [part.get_content_type() for part in message.iter_parts()] == ["text/plain", "text/html"]
    assert "<h1" in message.get_body(preferencelist=("html",)).get_content()
    assert "Destaques" in message.get_body(preferencelist=("html",)).get_content()
    assert "https://example.com/chuva" in message.get_body(preferencelist=("plain",)).get_content()


def test_html_escapa_conteudo_do_modelo_e_do_acervo():
    report = {"area": '<img src=x onerror=alert(1)>', "start": "2026-11-16", "end": "2026-11-16",
              "summary": '<script>alert(1)</script>', "highlights": [{"title": "Teste", "text": "Texto", "sources": [1]}],
              "closing": "Confira.", "articles": [{"title": "<b>Notícia</b>", "date": "2026-11-16",
              "category": "Eventos", "url": 'javascript:alert(1)'}]}
    rendered = agent.render_report_html(report)
    assert "<script>" not in rendered and "<img" not in rendered and "<b>Notícia" not in rendered
    assert 'href="javascript:' not in rendered
    assert "&lt;script&gt;" in rendered


def test_gmail_so_fica_pronto_com_usuario_e_senha_de_app(monkeypatch):
    values = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587", "SMTP_FROM": "pessoa@gmail.com", "SMTP_REQUIRE_AUTH": "1"}
    monkeypatch.setattr(agent, "settings", lambda: values)
    assert agent.capabilities()["smtp_ready"] is False
    values.update(SMTP_USER="pessoa@gmail.com", SMTP_PASSWORD="senha-de-teste")
    assert agent.capabilities()["smtp_ready"] is True


def test_agendamento_nao_duplica_envio(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "CONFIG", tmp_path / "agent_subscription.json")
    data = tmp_path / "web"
    data.mkdir()
    (data / "catalog.json").write_text(json.dumps({"snapshot_date": "2026-11-16"}), encoding="utf-8")
    monkeypatch.setattr(agent, "DATA", data)
    monkeypatch.setattr(agent, "settings", lambda: {"GEMINI_API_KEY": "test", "GEMINI_MODEL": "gemini-3.8-flash", "SMTP_HOST": "example.com", "SMTP_PORT": "587", "SMTP_FROM": "remetente@example.com", "SMTP_REQUIRE_AUTH": "0"})
    agent.save_subscription({"area": "chuva", "frequency": "daily", "email": "pessoa@example.com", "hour": "20:30", "weekday": 0})
    article = {"title": "Chuva", "date": "2026-11-16", "url": "https://example.com/chuva"}
    monkeypatch.setattr(agent, "select_articles", lambda *args, **kwargs: {"articles": [article], "start": "2026-11-16", "end": "2026-11-16"})
    monkeypatch.setattr(agent, "generate_report", lambda *args: {"highlights": [{"title": "Chuva"}]})
    done = threading.Event()
    sent = []

    def fake_send(*args):
        sent.append(args)
        done.set()

    monkeypatch.setattr(agent, "send_email", fake_send)
    moment = datetime(2026, 11, 16, 20, 30)
    assert agent.run_due(moment) is True
    assert done.wait(3)
    assert agent.run_due(moment) is False
    assert len(sent) == 1
    for _ in range(30):
        if not agent.status()["running"]:
            break
        time.sleep(0.05)
    assert agent.status()["last_error"] is None
    assert agent.load_subscription()["seen_urls"] == [article["url"]]


def test_rotas_locais_salvam_e_desativam_sem_enviar(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "CONFIG", tmp_path / "subscription.json")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        payload = {"area": "chuva", "frequency": "daily", "email": "pessoa@example.com", "hour": "20:30", "weekday": 0}
        denied = requests.post(base + "/api/agent/save", json=payload, headers={"Origin": "https://example.com"}, timeout=5)
        assert denied.status_code == 403
        saved = requests.post(base + "/api/agent/save", json=payload, headers={"Origin": base}, timeout=5)
        assert saved.status_code == 200
        assert requests.get(base + "/api/agent/status", timeout=5).json()["subscription"]["active"] is True
        disabled = requests.post(base + "/api/agent/disable", json={}, headers={"Origin": base}, timeout=5)
        assert disabled.status_code == 200
        assert agent.load_subscription()["active"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
