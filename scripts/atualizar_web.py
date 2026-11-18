"""Atualiza coleta, indices e graficos usados pela demonstracao web local."""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from projeto_pln import RAW_PATH, parse_date, public_article_count, read_jsonl, run_pipeline  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--since", help="Coleta publicacoes posteriores a AAAA-MM-DD")
    group.add_argument("--target", type=int, help="Total minimo de noticias publicas")
    group.add_argument("--recent", action="store_true", help="Atualizacao agendada desde a ultima data")
    args = parser.parse_args()
    previous = read_jsonl(RAW_PATH)
    if not previous:
        parser.error("Base inicial nao encontrada.")
    if args.target is not None and args.target < 1:
        parser.error("--target deve ser positivo.")
    if args.target is not None and public_article_count(previous) >= args.target:
        print(f"O acervo ja contem {public_article_count(previous)} noticias publicas.", flush=True)
        return
    if args.recent:
        dates = [parse_date(item.get("published_at", "")) for item in previous]
        newest = max(value.date() for value in dates if value)
        since = newest - timedelta(days=1)
    elif args.since:
        try:
            since = datetime.fromisoformat(args.since).date()
        except ValueError:
            parser.error("--since deve ter formato AAAA-MM-DD.")
    else:
        since = None
    if since is not None and since > date.today():
        parser.error("A data nao pode estar no futuro.")

    run_pipeline(since_date=since, target_public_count=args.target)
    summary = json.loads((ROOT / "reports/summary.json").read_text(encoding="utf-8"))
    if not summary.get("collection_complete"):
        raise RuntimeError("A coleta nao confirmou cobertura completa; veja reports/summary.json.")
    if args.target is not None and summary.get("public_articles", 0) < args.target:
        raise RuntimeError("A coleta terminou antes de atingir a quantidade desejada.")
    from representacao_textual import calcular_hash_base, carregar_base_nlp, carregar_manifest_indices

    current_hash = calcular_hash_base(carregar_base_nlp())
    indexed_hash = carregar_manifest_indices().get("semantic", {}).get("dataset_hash")
    if current_hash == indexed_hash and (ROOT / "web/data/results.json").exists():
        print("Sem alteracoes no acervo; indice e pagina ja estao atualizados.", flush=True)
        return
    from busca import indexar_busca
    from clustering import gerar_visualizacao_word2vec_k12
    from scripts.exportar_web import export as export_search
    from scripts.exportar_resultados_web import export as export_results

    print("Reindexando Word2Vec...", flush=True)
    indexar_busca(incluir_bert=False)
    print("Gerando graficos atuais...", flush=True)
    gerar_visualizacao_word2vec_k12()
    export_search()
    export_results()
    print("Pagina atualizada. Recarregue o navegador.", flush=True)


if __name__ == "__main__":
    main()
