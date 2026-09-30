"""Projeto completo: coleta, analise e pre-processamento de noticias.

Antes da primeira execucao, instale as dependencias descritas no README.md.
Depois, execute apenas: python projeto_pln.py
"""

import argparse
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd


# Configuracoes principais
BASE_URL = "https://blogdojaime.com.br/noticias/"
INITIAL_PAGES = 50
UPDATE_PAGES = 10
DELAY_SECONDS = 1.0
MINIMUM_WORDS = 20
RECENT_DAYS = 7
TASK_NAME = "ProjetoPLNNoticiasBlumenau"
TASK_TIME = "22:00"

PROJECT_DIR = Path(__file__).resolve().parent
RAW_PATH = PROJECT_DIR / "data/raw/noticias.jsonl"
PROCESSED_PATH = PROJECT_DIR / "data/processed/noticias.jsonl"
NLP_JSONL_PATH = PROJECT_DIR / "data/processed/noticias_nlp.jsonl"
REPORTS_PATH = PROJECT_DIR / "reports"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

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
    from bs4 import BeautifulSoup

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
    from bs4 import BeautifulSoup

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
    import requests

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


def read_jsonl(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def merge_by_url(previous_articles, collected_articles):
    """Acrescenta URLs novas e atualiza as URLs que ja estavam salvas."""
    articles_by_url = {article["url"]: article for article in previous_articles}
    articles_by_url.update({article["url"]: article for article in collected_articles})
    return list(articles_by_url.values())


def collect_articles(total_pages, previous_articles=None):
    import requests

    session = requests.Session()
    session.headers.update(HEADERS)
    articles = []
    previous_articles = previous_articles or []
    seen_urls = set()
    failed_pages = []
    failed_articles = 0

    for page in range(1, total_pages + 1):
        page_url = listing_url(page)
        try:
            links = extract_article_links(download(session, page_url), page_url)
        except requests.RequestException as error:
            failed_pages.append(page)
            print(f"Pagina {page:02d}/{total_pages}: erro na listagem ({error})", flush=True)
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

        # Na atualizacao, o checkpoint preserva o historico ja existente.
        checkpoint = merge_by_url(previous_articles, articles)
        write_jsonl(checkpoint, RAW_PATH)
        print(
            f"Pagina {page:02d}/{total_pages}: {collected_on_page} noticias "
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


def generate_reports(
    raw_articles,
    processed_articles,
    failed_pages,
    failed_articles,
    pages_requested,
    execution_mode,
    new_articles,
    updated_articles,
):
    raw_summary = describe(raw_articles)
    processed_summary = describe(processed_articles)
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "execution_mode": execution_mode,
        "pages_requested": pages_requested,
        "pages_collected": pages_requested - len(failed_pages),
        "failed_pages": failed_pages,
        "failed_articles": failed_articles,
        "new_articles": new_articles,
        "updated_articles": updated_articles,
        "raw": raw_summary,
        "processed": processed_summary,
        "removed_during_processing": len(raw_articles) - len(processed_articles),
    }

    REPORTS_PATH.mkdir(parents=True, exist_ok=True)
    (REPORTS_PATH / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return summary


# 3. Pre-processamento de PLN
def normalizar_tokens(tokens_da_frase):
    return [token.casefold() for token in tokens_da_frase if token.isalpha()]


def processar_nlp(articles):
    import spacy
    from nltk.corpus import stopwords
    from nltk.stem import RSLPStemmer
    from nltk.tokenize import word_tokenize

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
    return resultado


def summarize_period(name, dataframe):
    dates = pd.to_datetime(dataframe["published_at"], errors="coerce", utc=True)
    categories = Counter(dataframe["category"].fillna("Sem categoria"))
    terms = Counter(
        token
        for tokens in dataframe["tokens_sem_stopwords"]
        for token in tokens
    )
    return {
        "period": name,
        "start_date": dates.min().date().isoformat() if not dates.empty else "",
        "end_date": dates.max().date().isoformat() if not dates.empty else "",
        "articles": len(dataframe),
        "average_words": round(dataframe["word_count"].mean(), 2) if len(dataframe) else 0,
        "top_categories": "; ".join(
            f"{category}: {count}" for category, count in categories.most_common(5)
        ),
        "top_terms": "; ".join(
            f"{term}: {count}" for term, count in terms.most_common(10)
        ),
    }


def create_temporal_samples(dataframe):
    """Compara os sete dias mais recentes com o periodo anterior."""
    dates = pd.to_datetime(dataframe["published_at"], errors="coerce", utc=True)
    newest_date = dates.max().normalize()
    cutoff = newest_date - pd.Timedelta(RECENT_DAYS - 1, unit="D")

    recent = dataframe[dates >= cutoff].copy()
    previous = dataframe[dates < cutoff].copy()

    return {
        "reference_date": newest_date.date().isoformat(),
        "recent_period_start": cutoff.date().isoformat(),
        "recent_articles": len(recent),
        "previous_articles": len(previous),
        "periods": [
            summarize_period("ultimos_7_dias", recent),
            summarize_period("periodo_anterior", previous),
        ],
    }


def install_daily_schedule():
    """Instala no Windows a atualizacao diaria das 10 paginas mais recentes."""
    if sys.platform != "win32":
        raise RuntimeError("O agendamento automatico esta configurado para Windows.")

    python_path = Path(sys.executable).resolve()
    script_path = Path(__file__).resolve()
    task_command = f'"{python_path}" "{script_path}" --atualizar'
    subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN",
            TASK_NAME,
            "/TR",
            task_command,
            "/SC",
            "DAILY",
            "/ST",
            TASK_TIME,
            "/F",
        ],
        check=True,
    )
    print(f"Agendamento instalado: todos os dias as {TASK_TIME}.")
    print(f"Tarefa do Windows: {TASK_NAME}")


def run_pipeline(update_mode=False):
    previous_articles = read_jsonl(RAW_PATH) if update_mode else []
    if update_mode and not previous_articles:
        raise FileNotFoundError(
            "Base inicial nao encontrada. Execute primeiro: python projeto_pln.py"
        )

    pages_requested = UPDATE_PAGES if update_mode else INITIAL_PAGES
    execution_mode = "atualizacao_incremental" if update_mode else "coleta_inicial"
    print(
        f"1/4 - Coletando as ultimas {pages_requested} paginas "
        f"({execution_mode})...",
        flush=True,
    )
    collected_articles, failed_pages, failed_articles = collect_articles(
        pages_requested,
        previous_articles,
    )

    previous_urls = {article["url"] for article in previous_articles}
    collected_urls = {article["url"] for article in collected_articles}
    new_articles = len(collected_urls - previous_urls)
    updated_articles = len(collected_urls & previous_urls)
    raw_articles = (
        merge_by_url(previous_articles, collected_articles)
        if update_mode
        else collected_articles
    )

    processed_articles, duplicates, short_articles = remove_duplicates_and_short_articles(
        raw_articles
    )
    write_jsonl(raw_articles, RAW_PATH)
    write_jsonl(processed_articles, PROCESSED_PATH)

    print("\n2/4 - Gerando a analise exploratoria...", flush=True)
    summary = generate_reports(
        raw_articles,
        processed_articles,
        failed_pages,
        failed_articles,
        pages_requested,
        execution_mode,
        new_articles,
        updated_articles,
    )

    print("\n3/4 - Aplicando o pre-processamento de PLN...", flush=True)
    nlp_dataframe = processar_nlp(processed_articles)
    temporal_summary = create_temporal_samples(nlp_dataframe)
    summary["temporal_comparison"] = temporal_summary

    print("\n4/4 - Gerando Bag of Words, TF-IDF e clusters...", flush=True)
    from clustering import gerar_vetores_e_clusters

    clustered_dataframe, vectorization_summary = gerar_vetores_e_clusters(
        nlp_dataframe
    )
    summary["vectorization"] = vectorization_summary
    (REPORTS_PATH / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\nProcessamento concluido.")
    print(f"Modo: {execution_mode}")
    print(f"Paginas concluidas: {pages_requested - len(failed_pages)}/{pages_requested}")
    print(f"Noticias que falharam: {failed_articles}")
    print(f"Noticias novas: {new_articles}")
    print(f"Noticias existentes atualizadas: {updated_articles}")
    print(f"Noticias brutas no historico: {len(raw_articles)}")
    print(f"Noticias duplicadas removidas: {duplicates}")
    print(f"Noticias curtas removidas: {short_articles}")
    print(f"Noticias validas: {len(processed_articles)}")
    print(f"Noticias processadas para PLN: {len(nlp_dataframe)}")
    print(
        f"Clusters: {vectorization_summary['selected_clusters']} para "
        f"{len(clustered_dataframe)} noticias"
    )
    print(
        f"Recorte recente: {temporal_summary['recent_articles']} noticias; "
        f"periodo anterior: {temporal_summary['previous_articles']} noticias"
    )
    print(f"Campos ausentes na base valida: {summary['processed']['missing_fields']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--atualizar",
        action="store_true",
        help="Coleta 10 paginas e atualiza a base existente sem duplicar URLs",
    )
    parser.add_argument(
        "--agendar-diariamente",
        action="store_true",
        help="Cria uma tarefa do Windows para atualizar diariamente as 22:00",
    )
    parser.add_argument(
        "--agrupar",
        action="store_true",
        help="Regera vetores e clusters usando a base noticias_nlp.jsonl existente",
    )
    parser.add_argument(
        "--indexar-busca",
        action="store_true",
        help="Gera indices Word2Vec e BERT para a busca semantica",
    )
    parser.add_argument(
        "--sem-bert",
        action="store_true",
        help="Com --indexar-busca, gera somente o indice Word2Vec",
    )
    parser.add_argument(
        "--buscar",
        metavar="CONSULTA",
        help="Busca noticias nos indices existentes",
    )
    parser.add_argument(
        "--comparar-buscas",
        metavar="CONSULTA",
        help="Compara representacoes e metricas em uma matriz CSV",
    )
    parser.add_argument(
        "--classificar",
        action="store_true",
        help="Treina o classificador TF-IDF para as categorias das noticias",
    )
    parser.add_argument(
        "--metodo",
        choices=("bow", "tfidf", "word2vec", "bert"),
        default="tfidf",
        help="Representacao usada por --buscar (padrao: tfidf)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Quantidade de resultados de --buscar (padrao: 10)",
    )
    parser.add_argument(
        "--metrica",
        choices=("cosseno", "euclidiana", "manhattan"),
        default="cosseno",
        help="Metrica usada por --buscar (padrao: cosseno)",
    )
    args = parser.parse_args()

    if args.agendar_diariamente:
        install_daily_schedule()
    elif args.agrupar:
        from clustering import agrupar_base_existente

        agrupar_base_existente()
    elif args.indexar_busca:
        from busca import indexar_busca

        indexar_busca(incluir_bert=not args.sem_bert)
    elif args.buscar:
        from busca import buscar, imprimir_resultados

        imprimir_resultados(
            buscar(args.buscar, args.metodo, args.top_k, args.metrica)
        )
    elif args.comparar_buscas:
        from comparacao_buscas import gerar_matriz_comparacao, imprimir_comparacao

        matriz = gerar_matriz_comparacao(args.comparar_buscas, args.top_k)
        imprimir_comparacao(matriz)
    elif args.classificar:
        from classificacao import main as classificar_noticias

        classificar_noticias()
    else:
        run_pipeline(update_mode=args.atualizar)


if __name__ == "__main__":
    main()
