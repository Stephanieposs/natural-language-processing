"""Coletor reproduzível de notícias do Blog do Jaime."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://blogdojaime.com.br/"
USER_AGENT = "NLP-Blumenau-Academic-Collector/1.0 (educational use)"
SPACE_RE = re.compile(r"\s+")
ARTICLE_FIELDS = ("title", "published_at", "category", "content", "url", "collected_at")


@dataclass(frozen=True)
class Article:
    title: str
    published_at: str
    category: str
    content: str
    url: str
    collected_at: str

    @property
    def content_hash(self) -> str:
        normalized = normalize_for_hash(f"{self.title} {self.content}")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def to_record(self) -> dict[str, str | int]:
        record = asdict(self)
        record["content_hash"] = self.content_hash
        record["word_count"] = len(self.content.split())
        return record


def clean_text(value: str) -> str:
    """Remove espaços e quebras de linha redundantes sem alterar o conteúdo."""
    return SPACE_RE.sub(" ", value).strip()


def normalize_for_hash(value: str) -> str:
    """Normaliza texto para detectar republicações exatas com pequenas variações."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _first_text(soup: BeautifulSoup, selectors: Iterable[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node and clean_text(node.get_text(" ", strip=True)):
            return clean_text(node.get_text(" ", strip=True))
    return ""


def parse_article(html: str, url: str, collected_at: str | None = None) -> Article:
    """Extrai os campos, aceitando os layouts WordPress mais comuns do portal."""
    soup = BeautifulSoup(html, "html.parser")
    title = _first_text(soup, ("h1.entry-title", "article h1", "main h1", "h1"))
    content_node = next(
        (soup.select_one(s) for s in (".entry-content", ".post-content", "article") if soup.select_one(s)),
        None,
    )
    if content_node:
        for unwanted in content_node.select("script, style, nav, form, .sharedaddy, .social-share, .post-tags"):
            unwanted.decompose()
        paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in content_node.select("p")]
        content = "\n".join(p for p in paragraphs if p)
        if not content:
            content = clean_text(content_node.get_text(" ", strip=True))
    else:
        content = ""

    time_node = soup.select_one("time[datetime]")
    published = clean_text(time_node.get("datetime", "")) if time_node else _first_text(
        soup, ("time", ".entry-date", ".post-date")
    )
    category = _first_text(soup, (".cat-links a", "a[rel='category tag']", ".post-category a"))
    if not title:
        raise ValueError(f"Título não encontrado em {url}")
    return Article(
        title=title,
        published_at=published,
        category=category,
        content=content,
        url=url,
        collected_at=collected_at or datetime.now(timezone.utc).isoformat(),
    )


def extract_article_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = "article h2 a, article h3 a, h2.entry-title a, h3.entry-title a"
    links: list[str] = []
    expected_host = urlparse(page_url).netloc.removeprefix("www.")
    for node in soup.select(selectors):
        link = urljoin(page_url, node.get("href", "")).split("#", 1)[0]
        if urlparse(link).netloc.removeprefix("www.") == expected_host and link not in links:
            links.append(link)
    return links


class Collector:
    def __init__(self, delay: float = 1.0, timeout: float = 20.0) -> None:
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.mount("http://", HTTPAdapter(max_retries=retries))

    def get(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        time.sleep(self.delay)
        return response.text

    def collect(self, start_url: str, pages: int) -> Iterator[Article]:
        seen_urls: set[str] = set()
        for page in range(1, pages + 1):
            listing_url = start_url if page == 1 else urljoin(start_url.rstrip("/") + "/", f"page/{page}/")
            logging.info("Lendo página %s: %s", page, listing_url)
            try:
                links = extract_article_links(self.get(listing_url), listing_url)
            except requests.RequestException as error:
                logging.warning("Não foi possível ler a listagem %s: %s", listing_url, error)
                continue
            if not links:
                logging.warning("Nenhum link de notícia encontrado em %s", listing_url)
            for url in links:
            for url in extract_article_links(self.get(listing_url), listing_url):
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                try:
                    yield parse_article(self.get(url), url)
                except (requests.RequestException, ValueError) as error:
                    logging.warning("Não foi possível coletar %s: %s", url, error)


def deduplicate(articles: Iterable[Article], minimum_words: int = 0) -> tuple[list[Article], int, int]:
    unique: list[Article] = []
    hashes: set[str] = set()
    duplicates = short = 0
    for article in articles:
        if len(article.content.split()) < minimum_words:
            short += 1
            continue
        if article.content_hash in hashes:
            duplicates += 1
            continue
        hashes.add(article.content_hash)
        unique.append(article)
    return unique, duplicates, short


def read_jsonl(source: Path) -> list[Article]:
    """Lê um arquivo anterior; campos calculados extras são ignorados."""
    if not source.exists():
        return []
    articles: list[Article] = []
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                articles.append(Article(**{field: record.get(field, "") for field in ARTICLE_FIELDS}))
            except (json.JSONDecodeError, TypeError) as error:
                raise ValueError(f"Registro inválido em {source}:{line_number}") from error
    return articles


def merge_by_url(previous: Iterable[Article], collected: Iterable[Article]) -> list[Article]:
    """Acrescenta URLs novas e atualiza uma URL já conhecida sem duplicá-la."""
    merged: dict[str, Article] = {article.url: article for article in previous}
    merged.update({article.url: article for article in collected})
    return list(merged.values())


def write_jsonl(articles: Iterable[Article], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for article in articles:
            stream.write(json.dumps(article.to_record(), ensure_ascii=False) + "\n")
    temporary.replace(destination)


def write_csv(articles: Iterable[Article], destination: Path) -> None:
    records = [article.to_record() for article in articles]
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (*ARTICLE_FIELDS, "content_hash", "word_count")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    temporary.replace(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="Página inicial ou página de categoria")
    parser.add_argument("--pages", type=int, default=1, help="Quantidade de páginas de listagem")
    parser.add_argument("--delay", type=float, default=1.0, help="Intervalo entre requisições, em segundos")
    parser.add_argument("--minimum-words", type=int, default=20, help="Descartar textos menores que este limite")
    parser.add_argument("--output", type=Path, default=Path("data/processed/noticias.jsonl"))
    args = parser.parse_args()
    if args.pages < 1 or args.delay < 0 or args.minimum_words < 0:
        parser.error("pages deve ser positivo; delay e minimum-words não podem ser negativos")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raw_path = Path("data/raw/noticias.jsonl")
    previous = read_jsonl(raw_path)
    collected = list(Collector(args.delay).collect(args.url, args.pages))
    complete = merge_by_url(previous, collected)
    write_jsonl(complete, raw_path)
    clean, duplicates, short = deduplicate(complete, args.minimum_words)
    write_jsonl(clean, args.output)
    write_csv(clean, args.output.with_suffix(".csv"))
    logging.info(
        "Concluído: %d novas/atualizadas, %d no histórico, %d únicas, %d duplicadas e %d curtas. "
        "Dados brutos: %s",
        len(collected), len(complete), len(clean), duplicates, short, raw_path,
    )


if __name__ == "__main__":
    main()
