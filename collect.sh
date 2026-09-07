#!/usr/bin/env bash
# Coleta reproduzível do Blog do Jaime, categoria por categoria.
#
# Uso:
#   ./collect.sh                                  # plano completo, sequencial
#   ./collect.sh lote1 ocorrencias:15 tempo:12    # subconjunto nomeado (permite 2 lotes em paralelo)
#
# Variáveis opcionais: DELAY (padrão 1.5 s), MIN_WORDS (padrão 20).
# Cada categoria grava data/raw/parts/<cat>.jsonl (bruto incremental) e
# data/processed/parts/<cat>.jsonl; o log fica em data/raw/parts/logs/<cat>.log.
# Depois, consolide com: python3 merge_raw.py data/raw/parts/*.jsonl --minimum-words 20
#
# Evite mais de 2 lotes simultâneos: páginas de arquivo custam ~5 s ao servidor do portal.
set -u
cd "$(dirname "$0")"

BATCH="${1:-completo}"
shift || true
if [ "$#" -eq 0 ]; then
  set -- geral:2 noticias:12 destaques:12 ocorrencias:15 transito:10 eventos:15 \
         tempo:12 diversos:8 saude:10 esportes:10 falecidos:5 aniversarios:5
fi
DELAY="${DELAY:-1.5}"
MIN_WORDS="${MIN_WORDS:-20}"

mkdir -p data/raw/parts/logs data/processed/parts
LOG="data/raw/parts/logs/lote-$BATCH.log"

for spec in "$@"; do
  cat="${spec%%:*}"
  pages="${spec##*:}"
  if [ "$cat" = "geral" ]; then
    url="https://blogdojaime.com.br/noticias/"
  else
    url="https://blogdojaime.com.br/category/$cat/"
  fi
  echo "[$(date '+%F %T')] início $cat ($pages páginas) $url" >> "$LOG"
  python3 scraper.py --url "$url" --pages "$pages" --delay "$DELAY" --minimum-words "$MIN_WORDS" \
    --raw "data/raw/parts/$cat.jsonl" --output "data/processed/parts/$cat.jsonl" \
    > "data/raw/parts/logs/$cat.log" 2>&1
  status=$?
  warnings=$(grep -c WARNING "data/raw/parts/logs/$cat.log")
  summary=$(grep 'Concluído' "data/raw/parts/logs/$cat.log" | tail -1)
  echo "[$(date '+%F %T')] fim $cat exit=$status | avisos=$warnings | $summary" >> "$LOG"
done
echo "[$(date '+%F %T')] LOTE $BATCH CONCLUÍDO" >> "$LOG"
