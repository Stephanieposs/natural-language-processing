"""Projeto completo: coleta, analise e pre-processamento de noticias.

Antes da primeira execucao, instale as dependencias descritas no README.md.
Depois, execute apenas: python projeto_pln.py
"""

import csv
import hashlib
import json
import re
import statistics
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import spacy
from bs4 import BeautifulSoup
from nltk.corpus import stopwords
from nltk.stem import RSLPStemmer
from nltk.tokenize import word_tokenize


# Configuracoes principais
BASE_URL = "https://blogdojaime.com.br/noticias/"
TOTAL_PAGES = 50
DELAY_SECONDS = 1.0
MINIMUM_WORDS = 20
SAMPLE_SIZE = 20

RAW_PATH = Path("data/raw/noticias.jsonl")
PROCESSED_PATH = Path("data/processed/noticias.jsonl")
PROCESSED_CSV_PATH = Path("data/processed/noticias.csv")
NLP_JSONL_PATH = Path("data/processed/noticias_nlp.jsonl")
NLP_CSV_PATH = Path("data/processed/noticias_nlp.csv")
REPORTS_PATH = Path("reports")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

ARTICLE_FIELDS = (
    "title",
    "published_at",
    "category",
    "content",
    "url",
    "collected_at",
    "content_hash",
    "word_count",
)
REQUIRED_FIELDS = ("title", "published_at", "category", "content", "url")


# 1. Coleta das noticias
def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_for_hash(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def first_text(soup, selectors):
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            text = clean_text(element.get_text(" ", strip=True))
            if text:
                return text
    return ""


def json_ld_value(soup, keys):
    """Busca data ou categoria nos metadados da noticia."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            pending = [json.loads(script.string or "")]
        except json.JSONDecodeError:
            continue

        while pending:
            item = pending.pop()
            if isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, dict):
                for key in keys:
                    if item.get(key):
                        value = item[key]
                        return clean_text(str(value[0] if isinstance(value, list) else value))
                pending.extend(item.values())
    return ""


def parse_article(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title = first_text(soup, ["h1.entry-title", "article h1", "main h1", "h1"])

    content = ""
    content_element = soup.select_one(
        ".entry-content, .post-content, .elementor-widget-theme-post-content, article"
    )
    if content_element:
        for unwanted in content_element.select("script, style, nav, form, iframe"):
            unwanted.decompose()
        paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in content_element.select("p")]
        content = "\n".join(paragraph for paragraph in paragraphs if paragraph)
        if not content:
            content = clean_text(content_element.get_text(" ", strip=True))

    published_at = json_ld_value(soup, ["datePublished", "dateModified"])
    if not published_at:
        date_element = soup.select_one("time[datetime]")
        published_at = date_element.get("datetime", "") if date_element else first_text(
            soup, ["time", ".entry-date", ".post-date"]
        )

    category = json_ld_value(soup, ["articleSection"]) or first_text(
        soup,
        [
            ".cat-links a",
            "a[rel='category tag']",
            ".post-category a",
            ".elementor-post-info__item--type-terms a",
        ],
    )

    if not title:
        raise ValueError("Titulo nao encontrado")

    normalized = normalize_for_hash(f"{title} {content}")
    return {
        "title": title,
        "published_at": clean_text(published_at),
        "category": category,
        "content": content,
        "url": url,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "word_count": len(content.split()),
    }


def is_article_url(url):
    parsed = urlparse(url)
    if parsed.netloc.removeprefix("www.") != "blogdojaime.com.br":
        return False

    path = parsed.path.strip("/")
    if path in {"", "noticias", "contato", "anuncie-conosco"} or "/" in path:
        return False
    if path.startswith(("category", "tag", "author", "page", "wp-")):
        return False
    return not re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf)$", path, re.IGNORECASE)


def extract_article_links(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for element in soup.select("a[href]"):
        url = urljoin(page_url, element.get("href", "")).split("#", 1)[0]
        url = url.rstrip("/") + "/"
        if is_article_url(url) and url not in links:
            links.append(url)
    return links


def listing_url(page):
    if page == 1:
        return BASE_URL
    return f"{BASE_URL}?jsf=jet-engine:posts&pagenum={page}"


def download(session, url):
    """Faz ate tres tentativas para evitar perda por uma falha temporaria."""
    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            time.sleep(DELAY_SECONDS)
            return response.text
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2)


def write_jsonl(records, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def collect_articles():
    session = requests.Session()
    session.headers.update(HEADERS)
    articles = []
    seen_urls = set()
    failed_pages = []
    failed_articles = 0

    for page in range(1, TOTAL_PAGES + 1):
        page_url = listing_url(page)
        try:
            links = extract_article_links(download(session, page_url), page_url)
        except requests.RequestException as error:
            failed_pages.append(page)
            print(f"Pagina {page:02d}/{TOTAL_PAGES}: erro na listagem ({error})", flush=True)
            continue

        collected_on_page = 0
        for url in links:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                articles.append(parse_article(download(session, url), url))
                collected_on_page += 1
            except (requests.RequestException, ValueError) as error:
                failed_articles += 1
                print(f"  Erro em {url}: {error}", flush=True)

        # A coleta parcial fica salva caso a execucao seja interrompida.
        write_jsonl(articles, RAW_PATH)
        print(
            f"Pagina {page:02d}/{TOTAL_PAGES}: {collected_on_page} noticias "
            f"(total: {len(articles)})",
            flush=True,
        )

    if failed_pages:
        print(f"Paginas que falharam: {failed_pages}")
    if failed_articles:
        print(f"Noticias que falharam: {failed_articles}")
    return articles, failed_pages, failed_articles


def remove_duplicates_and_short_articles(articles):
    clean_articles = []
    seen_hashes = set()
    duplicates = 0
    short_articles = 0

    for article in articles:
        if article["word_count"] < MINIMUM_WORDS:
            short_articles += 1
        elif article["content_hash"] in seen_hashes:
            duplicates += 1
        else:
            seen_hashes.add(article["content_hash"])
            clean_articles.append(article)

    return clean_articles, duplicates, short_articles


def write_csv(records, path, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


# 2. Analise exploratoria
def parse_date(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def describe(articles):
    word_counts = [article.get("word_count", 0) for article in articles]
    urls = [article.get("url", "") for article in articles]
    hashes = [article.get("content_hash", "") for article in articles]
    dates = [parse_date(article.get("published_at", "")) for article in articles]
    dates = [date for date in dates if date]
    categories = Counter(article.get("category") or "Sem categoria" for article in articles)
    missing_fields = {
        field: sum(not article.get(field) for article in articles)
        for field in REQUIRED_FIELDS
    }

    return {
        "total_articles": len(articles),
        "unique_urls": len(set(urls)),
        "duplicate_urls": len(urls) - len(set(urls)),
        "duplicate_content_hashes": len(hashes) - len(set(hashes)),
        "short_articles": sum(count < MINIMUM_WORDS for count in word_counts),
        "missing_fields": missing_fields,
        "oldest_publication": min(dates).date().isoformat() if dates else None,
        "newest_publication": max(dates).date().isoformat() if dates else None,
        "word_count": {
            "minimum": min(word_counts) if word_counts else 0,
            "maximum": max(word_counts) if word_counts else 0,
            "mean": round(statistics.mean(word_counts), 2) if word_counts else 0,
            "median": statistics.median(word_counts) if word_counts else 0,
        },
        "categories": dict(categories.most_common()),
    }


def generate_reports(raw_articles, processed_articles, failed_pages, failed_articles):
    raw_summary = describe(raw_articles)
    processed_summary = describe(processed_articles)
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "pages_requested": TOTAL_PAGES,
        "pages_collected": TOTAL_PAGES - len(failed_pages),
        "failed_pages": failed_pages,
        "failed_articles": failed_articles,
        "raw": raw_summary,
        "processed": processed_summary,
        "removed_during_processing": len(raw_articles) - len(processed_articles),
    }

    REPORTS_PATH.mkdir(parents=True, exist_ok=True)
    (REPORTS_PATH / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    category_rows = [
        {"category": category, "count": count}
        for category, count in processed_summary["categories"].items()
    ]
    write_csv(category_rows, REPORTS_PATH / "category_distribution.csv", ["category", "count"])

    months = Counter(
        date.strftime("%Y-%m")
        for article in processed_articles
        if (date := parse_date(article.get("published_at", "")))
    )
    month_rows = [{"month": month, "count": months[month]} for month in sorted(months)]
    write_csv(month_rows, REPORTS_PATH / "news_by_month.csv", ["month", "count"])

    issues = []
    for article in raw_articles:
        missing = ", ".join(field for field in REQUIRED_FIELDS if not article.get(field))
        if missing or article.get("word_count", 0) < MINIMUM_WORDS:
            issues.append(
                {
                    "url": article.get("url", ""),
                    "missing_fields": missing,
                    "word_count": article.get("word_count", 0),
                }
            )
    write_csv(issues, REPORTS_PATH / "quality_issues.csv", ["url", "missing_fields", "word_count"])

    sample = []
    for article in processed_articles[:SAMPLE_SIZE]:
        sample.append(
            {
                "title": article.get("title", ""),
                "category": article.get("category", ""),
                "url": article.get("url", ""),
                "review_status": "",
                "review_notes": "",
            }
        )
    write_csv(
        sample,
        REPORTS_PATH / "review_sample.csv",
        ["title", "category", "url", "review_status", "review_notes"],
    )
    return summary


# 3. Pre-processamento de PLN
def normalizar_tokens(tokens_da_frase):
    return [token.casefold() for token in tokens_da_frase if token.isalpha()]


def processar_nlp(articles):
    stopwords_pt = set(stopwords.words("portuguese"))
    stemmer = RSLPStemmer()
    nlp = spacy.load("pt_core_news_sm")

    def processar_texto(texto):
        tokens = word_tokenize(texto, language="portuguese")
        tokens_normalizados = normalizar_tokens(tokens)
        tokens_sem_stopwords = [
            token for token in tokens_normalizados if token not in stopwords_pt
        ]
        documento = nlp(" ".join(tokens_sem_stopwords))

        return pd.Series(
            {
                "tokens": tokens,
                "tokens_normalizados": tokens_normalizados,
                "tokens_sem_stopwords": tokens_sem_stopwords,
                "lemas": [token.lemma_ for token in documento],
                "stems": [stemmer.stem(token) for token in tokens_sem_stopwords],
            }
        )

    noticias = pd.DataFrame(articles)
    noticias["texto_bruto"] = (
        noticias["title"].fillna("") + " " + noticias["content"].fillna("")
    ).str.strip()
    colunas_processadas = noticias["texto_bruto"].apply(processar_texto)
    resultado = pd.concat([noticias, colunas_processadas], axis=1)

    NLP_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    resultado.to_json(NLP_JSONL_PATH, orient="records", lines=True, force_ascii=False)
    resultado.to_csv(NLP_CSV_PATH, index=False, encoding="utf-8")
    return len(resultado)


def main():
    print(f"1/3 - Coletando as ultimas {TOTAL_PAGES} paginas...", flush=True)
    raw_articles, failed_pages, failed_articles = collect_articles()
    processed_articles, duplicates, short_articles = remove_duplicates_and_short_articles(
        raw_articles
    )
    write_jsonl(raw_articles, RAW_PATH)
    write_jsonl(processed_articles, PROCESSED_PATH)
    write_csv(processed_articles, PROCESSED_CSV_PATH, ARTICLE_FIELDS)

    print("\n2/3 - Gerando a analise exploratoria...", flush=True)
    summary = generate_reports(
        raw_articles,
        processed_articles,
        failed_pages,
        failed_articles,
    )

    print("\n3/3 - Aplicando o pre-processamento de PLN...", flush=True)
    nlp_count = processar_nlp(processed_articles)

    print("\nProcessamento concluido.")
    print(f"Paginas concluidas: {TOTAL_PAGES - len(failed_pages)}/{TOTAL_PAGES}")
    print(f"Noticias que falharam: {failed_articles}")
    print(f"Noticias brutas: {len(raw_articles)}")
    print(f"Noticias duplicadas removidas: {duplicates}")
    print(f"Noticias curtas removidas: {short_articles}")
    print(f"Noticias validas: {len(processed_articles)}")
    print(f"Noticias processadas para PLN: {nlp_count}")
    print(
        "Campos ausentes na base valida: "
        f"{summary['processed']['missing_fields']}"
    )


if __name__ == "__main__":
    main()
