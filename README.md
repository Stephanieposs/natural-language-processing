# Notícias locais de Blumenau — coleta para PLN

Projeto da Etapa Prática 1 de Processamento de Linguagem Natural. O coletor percorre
páginas do **Blog do Jaime**, extrai título, data, categoria, texto e URL, preserva
uma cópia bruta e gera uma base limpa em JSONL e CSV.

## Instalação e uso

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scraper.py --pages 5 --delay 1.5 --minimum-words 20
```

Por padrão, os resultados são gravados em:

- `data/raw/noticias.jsonl`: tudo o que foi coletado, para rastreabilidade;
- `data/processed/noticias.jsonl`: textos únicos e acima do limite mínimo;
- `data/processed/noticias.csv`: a mesma base em formato tabular.

As execuções são **incrementais**: antes de coletar, o programa lê
`data/raw/noticias.jsonl`. Notícias com URLs novas são acrescentadas ao histórico;
quando uma URL já existe, seu registro é atualizado. Depois, a base processada é
recalculada a partir de todo esse histórico. Assim, executar o scraper amanhã não
apaga as notícias salvas hoje. As gravações usam um arquivo temporário para evitar
deixar a base incompleta caso a escrita seja interrompida.

Cada registro contém `title`, `published_at`, `category`, `content`, `url`,
`collected_at`, `content_hash` e `word_count`. É possível usar uma categoria como
ponto de partida com `--url URL_DA_CATEGORIA`, embora a página geral produza uma
base mais diversa.

## Critérios de preparação

- A deduplicação usa SHA-256 do título e conteúdo após conversão para minúsculas,
  remoção de acentos e pontuação. A URL não faz parte da chave, portanto uma
  republicação em outra URL é identificada.
- Textos curtos são mantidos na base bruta e removidos apenas da base processada.
- O HTML é descartado, mas pontuação e capitalização do texto são preservadas. A
  tokenização e a remoção de stopwords devem ser feitas depois, de acordo com a
  tarefa de PLN, evitando perda prematura de informação.
- O intervalo configurável entre requisições reduz a carga sobre o portal. Antes
  de uma coleta ampla, confira os termos de uso e o `robots.txt` da fonte.

## Testes

```bash
pip install -r requirements-dev.txt
pytest -q
```

Os testes usam HTML local e não fazem requisições ao site.

## Análise exploratória e revisão manual

Depois de uma coleta piloto, gere o relatório com:

```bash
python analyze.py
```

O diretório `reports/` receberá o resumo geral em JSON, distribuições por categoria
e mês em CSV, uma lista de problemas de qualidade, uma amostra para conferência
manual e gráficos SVG. Abra `reports/review_sample.csv`, compare cada item com sua
URL e preencha `review_status` (`ok` ou `erro`) e `review_notes`. Os SVGs não exigem
Matplotlib e podem ser abertos diretamente no navegador.

Fluxo inicial recomendado:

```bash
python scraper.py --pages 10 --delay 1.5 --minimum-words 20
python analyze.py --minimum-words 20 --sample-size 20
```

Se a coleta for interrompida por rede, execute novamente: o histórico incremental
evita a perda das notícias que já tenham sido salvas em uma execução concluída.

## Pré-processamento para PLN

Após revisar a qualidade da coleta, crie uma representação derivada para modelos:

```bash
python preprocess.py
```

O comando lê `data/processed/noticias.jsonl` e grava
`data/processed/noticias_nlp.jsonl`. Os campos originais são preservados e quatro
campos são acrescentados: `text_normalized`, `tokens`,
`tokens_without_stopwords` e `text_for_model`. A normalização mantém acentos, une
título e conteúdo e não aplica stemming ou lematização automaticamente.

Use `--keep-stopwords` quando a tarefa precisar preservar todas as palavras:

```bash
python preprocess.py --keep-stopwords
```

Manter as duas representações permite comparar abordagens sem perder o texto
original, algo importante para NER, sumarização e apresentação das fontes.
