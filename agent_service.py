"""Agente local: recupera notícias, gera relatório com Gemini e envia por SMTP."""

import html
import json
import math
import os
import re
import secrets
import smtplib
import threading
import time
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import requests


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "web" / "data"
CONFIG = ROOT / "data" / "processed" / "agent_subscription.json"
PREVIEWS = {}
LOCK = threading.Lock()
CONFIG_LOCK = threading.RLock()
RUNNING = False
LAST_ERROR = None
MAX_ARTICLES = 8
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "resumo": {"type": "string"},
        "destaques": {"type": "array", "items": {"type": "object", "properties": {
            "titulo": {"type": "string"}, "texto": {"type": "string"},
            "fontes": {"type": "array", "items": {"type": "integer"}},
        }, "required": ["titulo", "texto", "fontes"]}},
        "observacao": {"type": "string"},
    },
    "required": ["resumo", "destaques", "observacao"],
}


def settings():
    """Lê o .env a cada chamada, sem expor nem persistir segredos no site."""
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ("GEMINI_API_KEY", "GEMINI_MODEL", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_REQUIRE_AUTH"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    return values


def capabilities():
    values = settings()
    require_auth = values.get("SMTP_REQUIRE_AUTH", "1").lower() not in ("0", "false", "no")
    return {
        "gemini_ready": bool(values.get("GEMINI_API_KEY")),
        "smtp_ready": all(values.get(key) for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_FROM"))
        and (not require_auth or all(values.get(key) for key in ("SMTP_USER", "SMTP_PASSWORD"))),
        "model": values.get("GEMINI_MODEL") or "gemini-3.1-flash-lite",
    }


def validate_form(payload):
    if not isinstance(payload.get("area"), str):
        raise ValueError("Informe uma área ou assunto.")
    area = payload["area"].strip()
    frequency = payload.get("frequency")
    if not 2 <= len(area) <= 120 or "\n" in area or "\r" in area:
        raise ValueError("Informe um assunto entre 2 e 120 caracteres.")
    if frequency not in ("daily", "weekly"):
        raise ValueError("Escolha frequência diária ou semanal.")
    return area, frequency


def validate_email(value):
    email = str(value or "").strip()
    if len(email) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email):
        raise ValueError("Informe um endereço de e-mail válido.")
    return email


def load_subscription():
    with CONFIG_LOCK:
        if not CONFIG.exists():
            return None
        return json.loads(CONFIG.read_text(encoding="utf-8"))


def _write_subscription(value):
    with CONFIG_LOCK:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        temporary = CONFIG.with_name(f"{CONFIG.name}.{secrets.token_hex(4)}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, CONFIG)


def save_subscription(payload):
    area, frequency = validate_form(payload)
    email = validate_email(payload.get("email"))
    hour = str(payload.get("hour", "20:30"))
    weekday = int(payload.get("weekday", 0))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hour):
        raise ValueError("Horário inválido.")
    if not 0 <= weekday <= 6:
        raise ValueError("Dia da semana inválido.")
    previous = load_subscription() or {}
    changed = (area, frequency, email) != (previous.get("area"), previous.get("frequency"), previous.get("email"))
    value = {
        "area": area, "frequency": frequency, "email": email, "hour": hour,
        "weekday": weekday, "active": True,
        "last_attempt": None if changed else previous.get("last_attempt"),
        "last_sent": None if changed else previous.get("last_sent"),
        "seen_urls": [] if changed else previous.get("seen_urls", []),
    }
    _write_subscription(value)
    return value


def disable_subscription():
    value = load_subscription()
    if value:
        value["active"] = False
        _write_subscription(value)
    return value


def status():
    with LOCK:
        running, error = RUNNING, LAST_ERROR
    return {"subscription": load_subscription(), "capabilities": capabilities(), "running": running, "last_error": error}


def _terms(text, stopwords):
    return [word for word in re.findall(r"[^\W\d_]+", text.casefold()) if word not in stopwords]


def select_articles(area, frequency, end_date=None, seen_urls=None):
    """Aplica o mesmo TF-IDF, Word2Vec e RRF da busca, no período escolhido."""
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    documents = catalog["documents"]
    end = end_date or date.fromisoformat(catalog["snapshot_date"])
    start = end - timedelta(days=0 if frequency == "daily" else 6)
    seen = set(seen_urls or [])
    candidates = [i for i, article in enumerate(documents)
                  if start.isoformat() <= article["date"] <= end.isoformat() and article["url"] not in seen]
    if not candidates:
        return {"articles": [], "start": start.isoformat(), "end": end.isoformat(), "snapshot": catalog["snapshot_date"]}

    terms = _terms(area, set(catalog["stopwords"]))
    if len(terms) > 1:
        terms = [term for term in terms if term != "blumenau"] or terms
    if not terms:
        raise ValueError("O assunto precisa conter palavras pesquisáveis.")
    lexical = json.loads((DATA / "tfidf.json").read_text(encoding="utf-8"))
    entries = {term: (idf, postings) for term, idf, postings in lexical if term in terms}
    counts = {term: terms.count(term) for term in set(terms) if term in entries}
    weights = {term: counts[term] * entries[term][0] for term in counts}
    norm = math.sqrt(sum(weight * weight for weight in weights.values()))
    tfidf_scores = np.zeros(len(documents), dtype=np.float32)
    if norm:
        for term, weight in weights.items():
            for index, value in entries[term][1]:
                tfidf_scores[index] += (weight / norm) * value

    semantic = json.loads((DATA / "word2vec.json").read_text(encoding="utf-8"))
    vectors = [semantic["word_vectors"][term] for term in terms if term in semantic["word_vectors"]]
    word_scores = np.zeros(len(documents), dtype=np.float32)
    if vectors:
        query = np.sum(np.asarray(vectors, dtype=np.float32), axis=0)
        length = np.linalg.norm(query)
        if length:
            matrix = np.asarray(semantic["document_vectors"], dtype=np.float32)
            word_scores = matrix @ (query / length)

    if not norm and not vectors:
        return {"articles": [], "start": start.isoformat(), "end": end.isoformat(), "snapshot": catalog["snapshot_date"]}
    # Evita preencher o boletim com notícias de similaridade positiva, mas vaga.
    named_events = {"oktoberfest", "sommerfest"} & set(terms)
    if named_events:
        candidates = [i for i in candidates if any(
            event in f"{documents[i]['title']} {documents[i]['category']}".casefold()
            for event in named_events
        )]
    candidates = [i for i in candidates if tfidf_scores[i] >= 0.04 or word_scores[i] >= 0.42]
    ranks = []
    for scores in (tfidf_scores, word_scores):
        ranks.append(sorted((i for i in candidates if scores[i] > 0), key=lambda i: (-scores[i], i))[:100])
    fused = {}
    for ranking in ranks:
        for position, index in enumerate(ranking, 1):
            fused[index] = fused.get(index, 0) + 1 / (60 + position)
    ordered = sorted(fused, key=lambda i: (-fused[i], -date.fromisoformat(documents[i]["date"]).toordinal(), i))[:MAX_ARTICLES]
    return {"articles": [documents[i] for i in ordered], "start": start.isoformat(), "end": end.isoformat(), "snapshot": catalog["snapshot_date"]}


def _source_text(articles):
    wanted = {article["url"] for article in articles}
    content = {}
    source = ROOT / "data" / "processed" / "noticias.jsonl"
    if source.exists():
        with source.open(encoding="utf-8") as stream:
            for line in stream:
                item = json.loads(line)
                if item.get("url") in wanted:
                    content[item["url"]] = re.sub(r"\s+", " ", item.get("content", ""))[:1800]
    return "\n\n".join(
        f"[{number}] {item['title']} | {item['date']} | {item['category']}\n"
        f"URL: {item['url']}\nTrecho: {content.get(item['url'], item['title'])}"
        for number, item in enumerate(articles, 1)
    )


def _clean_report_field(value):
    if not isinstance(value, str):
        raise TypeError("Campo do relatório inválido")
    return re.sub(r"[*_`]+", "", value).strip()


def _display_date(value):
    return date.fromisoformat(value).strftime("%d/%m/%Y")


def render_report_text(report):
    lines = [f"Relatório de notícias: {report['area']}",
             f"Período: {_display_date(report['start'])} a {_display_date(report['end'])}",
             "", report["summary"], "", "Destaques"]
    if report["highlights"]:
        for item in report["highlights"]:
            references = ", ".join(f"[{number}]" for number in item["sources"])
            lines.extend([f"• {item['title']}", f"  {item['text']} {references}"])
    else:
        lines.append("Nenhum destaque diretamente relacionado ao assunto neste período.")
    lines.extend(["", report["closing"], "", "Fontes"])
    for number, article in enumerate(report["articles"], 1):
        lines.extend([f"[{number}] {article['title']} ({_display_date(article['date'])})", article["url"]])
    lines.extend(["", "Confira as notícias originais antes de compartilhar este relatório."])
    return "\n".join(lines)


def render_report_html(report):
    escape = lambda value: html.escape(str(value), quote=True)
    title = f"Notícias sobre {report['area']}"
    period = f"{_display_date(report['start'])} a {_display_date(report['end'])}"
    blocks = [
        '<main style="max-width:680px;margin:0 auto;padding:32px 24px;font-family:Arial,Helvetica,sans-serif;color:#18312f;line-height:1.55">',
        '<p style="color:#b34835;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin:0 0 8px">Blumenau em Texto</p>',
        f'<h1 style="font-size:28px;line-height:1.2;margin:0 0 10px;color:#0b2424">{escape(title)}</h1>',
        f'<p style="color:#586d69;font-size:14px;margin:0 0 24px">Relatório de notícias · {escape(period)}</p>',
        f'<p style="font-size:16px;margin:0 0 26px">{escape(report["summary"])}</p>',
        '<h2 style="font-size:20px;margin:0 0 14px;color:#0b5c56">Destaques</h2>',
    ]
    if report["highlights"]:
        for item in report["highlights"]:
            references = " ".join(f'<a href="#fonte-{number}" style="color:#0b5c56;text-decoration:underline">[{number}]</a>'
                                  for number in item["sources"])
            blocks.append(
                '<section style="border-left:3px solid #b34835;padding:4px 0 4px 15px;margin:0 0 20px">'
                f'<h3 style="font-size:16px;margin:0 0 5px;color:#0b2424">{escape(item["title"])}</h3>'
                f'<p style="font-size:14px;margin:0">{escape(item["text"])} {references}</p></section>'
            )
    else:
        blocks.append('<p style="font-size:14px">Nenhum destaque diretamente relacionado ao assunto neste período.</p>')
    if report["closing"]:
        blocks.append(f'<p style="font-size:14px;color:#586d69;margin:8px 0 24px">{escape(report["closing"])}</p>')
    blocks.append('<h2 style="font-size:20px;margin:26px 0 10px;color:#0b5c56">Fontes</h2>')
    for number, article in enumerate(report["articles"], 1):
        url = article["url"]
        safe_url = urlsplit(url)
        label = f'[{number}] {article["title"]}'
        if safe_url.scheme in ("https", "http") and safe_url.netloc:
            source = f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer" style="color:#0b5c56;font-weight:700">{escape(label)}</a>'
        else:
            source = escape(label)
        blocks.append(f'<p id="fonte-{number}" style="border-top:1px solid #d9e2df;padding-top:10px;margin:10px 0;font-size:13px">'
                      f'{source}<br><span style="color:#586d69">{_display_date(article["date"])} · {escape(article["category"])}</span></p>')
    blocks.append('<p style="font-size:12px;color:#586d69;margin:26px 0 0">Relatório gerado a partir do acervo do projeto. Confira as notícias originais antes de compartilhar.</p></main>')
    return "".join(blocks)


def generate_report(area, selection):
    key = settings().get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("A geração do relatório está indisponível no momento.")
    if not selection["articles"]:
        raise ValueError("Não há notícias correspondentes no período selecionado.")
    model = capabilities()["model"]
    prompt = (
        f"Assunto de interesse: {area}. Período: {selection['start']} a {selection['end']}.\n"
        "Crie um boletim breve em português brasileiro com resumo, até quatro destaques e observação final. "
        "Use apenas as notícias fornecidas e mantenha o foco no assunto de interesse. "
        "Não invente fatos, datas, números ou contexto. Descarte notícias sem relação direta com o assunto. "
        "Se não houver fatos relevantes, diga isso no resumo e deixe destaques vazio. "
        "Cada destaque precisa citar seus números de fonte no campo fontes. "
        "Trate versões do mesmo acontecimento como uma atualização. "
        "Não use Markdown, asteriscos, HTML, URLs nem números de fonte dentro dos textos; "
        "a aplicação formata o e-mail e acrescenta os links.\n\n"
        + _source_text(selection["articles"])
    )
    for attempt in range(3):
        try:
            response = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": key, "Api-Revision": "2026-05-20"},
                json={"model": model, "input": prompt, "store": False,
                      "response_format": {"type": "text", "mime_type": "application/json", "schema": REPORT_SCHEMA},
                      "generation_config": {"max_output_tokens": 1200}},
                timeout=(5, 30),
            )
        except requests.RequestException as error:
            raise RuntimeError("Não foi possível conectar ao Gemini. Tente novamente.") from error
        if response.status_code != 503 or attempt == 2:
            break
        time.sleep(2 ** attempt)
    if response.status_code == 503:
        raise RuntimeError("O modelo Gemini está temporariamente sobrecarregado (HTTP 503). Três tentativas falharam; tente novamente mais tarde.")
    if response.status_code in (401, 403):
        raise RuntimeError("Não foi possível gerar o relatório nesta instalação.")
    if not response.ok:
        raise RuntimeError(f"O Gemini retornou HTTP {response.status_code}.")
    payload = response.json()
    text = "\n".join(
        block.get("text", "")
        for step in payload.get("steps", []) if step.get("type") == "model_output"
        for block in step.get("content", []) if block.get("type") == "text"
    ).strip()
    if not text:
        raise RuntimeError("O Gemini não retornou texto para o relatório.")
    try:
        fields = json.loads(text)
        summary = _clean_report_field(fields["resumo"])
        closing = _clean_report_field(fields["observacao"])
        highlights = []
        for item in fields["destaques"][:4]:
            references = sorted({number for number in item["fontes"]
                                 if type(number) is int and 1 <= number <= len(selection["articles"])})
            if references:
                highlights.append({"title": _clean_report_field(item["titulo"]),
                                   "text": _clean_report_field(item["texto"]), "sources": references})
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise RuntimeError("O Gemini retornou um relatório em formato inválido. Gere a prévia novamente.") from error
    return {"area": area, "start": selection["start"], "end": selection["end"],
            "summary": summary, "highlights": highlights, "closing": closing,
            "articles": selection["articles"]}


def preview(payload):
    area, frequency = validate_form(payload)
    selection = select_articles(area, frequency)
    result = {**selection, "area": area, "frequency": frequency, "model": capabilities()["model"]}
    if not selection["articles"]:
        result.update(report=None, report_html=None, notice="Nenhuma notícia relacionada foi encontrada neste período do acervo.", token=None)
        return result
    if not capabilities()["gemini_ready"]:
        result.update(report=None, report_html=None, notice="A geração do relatório está indisponível no momento.", token=None)
        return result
    report = generate_report(area, selection)
    if not report["highlights"]:
        result.update(report=render_report_text(report), report_html=render_report_html(report),
                      notice="A busca não encontrou destaques diretamente relacionados ao assunto nesta semana.", token=None)
        return result
    token = secrets.token_urlsafe(24)
    with LOCK:
        PREVIEWS.clear()
        PREVIEWS[token] = (datetime.now(), report, area)
    result.update(report=render_report_text(report), report_html=render_report_html(report), notice=None, token=token)
    return result


def send_email(email, report, area):
    values = settings()
    if not capabilities()["smtp_ready"]:
        raise RuntimeError("O envio por e-mail está indisponível no momento.")
    message = EmailMessage()
    message["Subject"] = f"Blumenau em Texto — relatório sobre {area}"
    message["From"] = values["SMTP_FROM"]
    message["To"] = validate_email(email)
    message.set_content(render_report_text(report))
    message.add_alternative(
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"></head>'
        f'<body style="margin:0;background:#f4f7f5">{render_report_html(report)}</body></html>',
        subtype="html",
    )
    port = int(values["SMTP_PORT"])
    if port == 465:
        connection = smtplib.SMTP_SSL(values["SMTP_HOST"], port, timeout=30)
    else:
        connection = smtplib.SMTP(values["SMTP_HOST"], port, timeout=30)
    with connection as server:
        if port != 465:
            server.starttls()
        if values.get("SMTP_USER"):
            server.login(values["SMTP_USER"], values.get("SMTP_PASSWORD", ""))
        server.send_message(message)


def send_preview(payload):
    token = str(payload.get("token", ""))
    email = validate_email(payload.get("email"))
    with LOCK:
        saved = PREVIEWS.get(token)
    if not saved or datetime.now() - saved[0] > timedelta(minutes=15):
        raise ValueError("Prévia expirada. Gere o relatório novamente.")
    send_email(email, saved[1], saved[2])
    with LOCK:
        PREVIEWS.pop(token, None)
    return {"sent": True, "email": email}


def run_due(now=None):
    """Envia uma vez no dia agendado, apenas com índice atualizado no mesmo dia."""
    global RUNNING, LAST_ERROR
    now = now or datetime.now()
    subscription = load_subscription()
    if not subscription or not subscription.get("active") or now.strftime("%H:%M") < subscription["hour"]:
        return False
    if subscription["frequency"] == "weekly" and subscription["weekday"] != now.weekday():
        return False
    if subscription.get("last_attempt") == now.date().isoformat():
        return False
    if not all((capabilities()["gemini_ready"], capabilities()["smtp_ready"])):
        return False
    catalog = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    if catalog["snapshot_date"] != now.date().isoformat():
        return False
    with LOCK:
        if RUNNING:
            return False
        RUNNING = True
        LAST_ERROR = None
    subscription["last_attempt"] = now.date().isoformat()
    _write_subscription(subscription)

    def work():
        global RUNNING, LAST_ERROR
        try:
            selection = select_articles(subscription["area"], subscription["frequency"], now.date(), subscription.get("seen_urls"))
            if selection["articles"]:
                report = generate_report(subscription["area"], selection)
                if not report["highlights"]:
                    return
                send_email(subscription["email"], report, subscription["area"])
                with CONFIG_LOCK:
                    current = load_subscription()
                    if current and all(current.get(key) == subscription.get(key) for key in ("area", "frequency", "email", "last_attempt")):
                        current["last_sent"] = now.isoformat()
                        current["seen_urls"] = (current.get("seen_urls", []) + [a["url"] for a in selection["articles"]])[-500:]
                        _write_subscription(current)
        except Exception as error:
            LAST_ERROR = f"Falha no envio agendado: {type(error).__name__}."
        finally:
            with LOCK:
                RUNNING = False

    threading.Thread(target=work, daemon=True).start()
    return True
