# Noticias de Blumenau - projeto de PLN

O projeto coleta as noticias das 50 paginas mais recentes do Blog do Jaime,
remove registros repetidos ou muito curtos, gera uma analise exploratoria e
aplica as etapas basicas de Processamento de Linguagem Natural.

Todo o fluxo usado para entrega esta no arquivo `projeto_pln.py`.

## Instalacao

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m nltk.downloader punkt punkt_tab stopwords rslp
python -m spacy download pt_core_news_sm
```

## Execucao

Execute somente:

```powershell
python projeto_pln.py
```

O programa realiza, nesta ordem:

1. coleta das 50 paginas;
2. remocao de duplicatas e textos com menos de 20 palavras;
3. analise da quantidade, categorias, datas e qualidade dos textos;
4. tokenizacao;
5. normalizacao;
6. remocao de stopwords;
7. lematizacao;
8. stemming;
9. exportacao dos resultados.

Durante a coleta, o arquivo bruto e atualizado ao final de cada pagina. Assim,
uma interrupcao nao apaga as paginas que ja foram coletadas.

## Arquivos gerados

- `data/raw/noticias.jsonl`: noticias coletadas nas 50 paginas;
- `data/processed/noticias.jsonl`: noticias validas;
- `data/processed/noticias.csv`: noticias validas em CSV;
- `data/processed/noticias_nlp.jsonl`: noticias com as etapas de PLN;
- `data/processed/noticias_nlp.csv`: dados de PLN em CSV;
- `reports/summary.json`: resumo da base;
- `reports/category_distribution.csv`: quantidade por categoria;
- `reports/news_by_month.csv`: quantidade por mes;
- `reports/quality_issues.csv`: registros com problemas;
- `reports/review_sample.csv`: amostra para revisao manual.

## Campos de PLN

Cada noticia processada possui:

- `texto_bruto`;
- `tokens`;
- `tokens_normalizados`;
- `tokens_sem_stopwords`;
- `lemas`;
- `stems`.

As configuracoes principais ficam no inicio de `projeto_pln.py`:

- `TOTAL_PAGES = 50`;
- `DELAY_SECONDS = 1.0`;
- `MINIMUM_WORDS = 20`.
