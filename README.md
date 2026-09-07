# Notícias locais de Blumenau — coleta e preparação para PLN

Projeto da Etapa Prática 1 de Processamento de Linguagem Natural (FURB). O objetivo é
construir uma **base textual de notícias locais de Blumenau e região** a partir do portal
[Blog do Jaime](https://blogdojaime.com.br), organizada e pré-processada para tarefas
futuras de PLN: classificação por assunto, extração de entidades (NER), recuperação de
informações, sumarização/agrupamento e um chatbot fundamentado nas notícias.

O pipeline tem quatro etapas, todas reproduzíveis por linha de comando:

| Etapa | Script | Entrada → Saída |
|-------|--------|-----------------|
| Coleta | `scraper.py` / `collect.sh` | páginas HTML → `data/raw/parts/<categoria>.jsonl` |
| Consolidação | `merge_raw.py` | arquivos parciais → `data/raw/noticias.jsonl`, `data/processed/noticias.jsonl` + `.csv` |
| Análise exploratória | `analyze.py` | base bruta e processada → `reports/` |
| Pré-processamento | `preprocess.py` | base processada → `data/processed/noticias_nlp.jsonl` |

O acompanhamento das tarefas e o registro de decisões estão em [`TASKS.md`](TASKS.md).

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependências: apenas `requests` e `beautifulsoup4`. Nenhum download de modelos ou
corpora é necessário; a lista de stopwords está embutida no código.

## Fonte de dados e forma de coleta

O Blog do Jaime é um portal WordPress com notícias sobre Blumenau e municípios vizinhos
(Gaspar, Indaial, Pomerode, Timbó...). Cada notícia expõe metadados estruturados em
JSON-LD (`datePublished`, `articleSection`), que o coletor usa como fonte principal para
data e categoria, com seletores HTML como alternativa.

Reconhecimento feito antes da coleta ampla (2026-09-06):

- `robots.txt` responde 200 com corpo vazio: nenhuma restrição declarada. Mesmo assim, o
  coletor usa intervalo entre requisições (`--delay`) e, no máximo, dois processos simultâneos.
- O portal devolve **403 para User-Agent genérico**; o coletor envia um UA de navegador comum.
- A listagem geral `/noticias/` tem apenas **duas páginas reais** (16 links cada); da terceira
  em diante repete as notícias mais recentes. Por isso a coleta é feita pelas **páginas de
  categoria** (`/category/<nome>/`), que são arquivos WordPress reais com 10 notícias por
  página e paginação profunda.
- Existem 11 categorias: Ocorrências, Eventos, Destaques, Tempo, Falecidos, Aniversários,
  Notícias, Diversos, Saúde, Esportes e Trânsito.
- O acervo completo tem cerca de **49 mil posts** (informado pela API REST do WordPress).
  A base coletada é, portanto, uma amostra das publicações mais recentes de cada categoria.
- Páginas de arquivo custam ~5 s ao servidor; páginas de notícia vêm do cache em ~0,2 s.
  Quatro coletas simultâneas provocaram timeouts, o que motivou o limite de dois lotes.

### Coleta

```bash
# uma listagem específica
python scraper.py --url https://blogdojaime.com.br/category/tempo/ --pages 12 --delay 1.5 --minimum-words 20 \
  --raw data/raw/parts/tempo.jsonl --output data/processed/parts/tempo.jsonl

# plano completo (todas as categorias, sequencial) ou um lote nomeado
./collect.sh
./collect.sh lote1 ocorrencias:15 eventos:15 tempo:12 transito:10
```

Cada registro contém `title`, `published_at`, `category`, `content`, `url`, `collected_at`,
`content_hash` e `word_count`. As execuções são **incrementais** por arquivo `--raw`: URLs
novas são acrescentadas e URLs conhecidas são atualizadas, sem apagar o histórico. As
gravações passam por um arquivo temporário para nunca deixar a base pela metade.

Gravar **um arquivo por categoria de listagem** (`data/raw/parts/<categoria>.jsonl`) preserva
a proveniência: sabe-se em qual listagem cada notícia foi encontrada, o que permite comparar
com a categoria declarada pelo portal (uma notícia pode pertencer a várias categorias; o
campo `category` guarda a primeira do JSON-LD). Os logs de cada execução ficam em
`data/raw/parts/logs/`.

### Consolidação

```bash
python merge_raw.py data/raw/parts/*.jsonl --minimum-words 20
```

Une os arquivos parciais (e o histórico anterior, se existir) por URL em
`data/raw/noticias.jsonl`, depois aplica os filtros e grava `data/processed/noticias.jsonl`
e `data/processed/noticias.csv`.

## Critérios de limpeza e organização

- **Deduplicação por conteúdo**: SHA-256 do título + conteúdo após minúsculas, remoção de
  acentos e pontuação. A URL não entra na chave, então republicações em outra URL são
  detectadas. Isso importa porque o portal **republica a mesma nota de serviço em dias
  consecutivos** com URLs terminadas em `-2`, `-3`, `-4` (horários de unidades de saúde,
  funcionamento de serviços, etc.).
- **Textos curtos** (`word_count < 20`) são mantidos na base bruta, para rastreabilidade,
  e removidos apenas da base processada.
- **HTML descartado, texto preservado**: pontuação, capitalização e acentos ficam intactos
  na base processada. Tokenização e remoção de stopwords acontecem só na etapa seguinte,
  para não perder informação necessária a NER, sumarização e exibição das fontes.

## Análise exploratória e revisão manual

```bash
python analyze.py --minimum-words 20 --sample-size 20 --top-terms 30
```

Arquivos gerados em `reports/`:

| Arquivo | Conteúdo |
|---------|----------|
| `summary.json` | totais, campos ausentes, datas inválidas, período coberto, estatísticas de tamanho, distribuição por categoria e tamanho do vocabulário |
| `category_distribution.csv` | notícias por categoria (base processada) |
| `news_by_month.csv` | notícias por mês de publicação |
| `top_terms.csv` | termos mais frequentes no geral e por categoria (sem stopwords e sem números) |
| `quality_issues.csv` | registros brutos com campos ausentes ou texto curto |
| `review_sample.csv` | amostra espalhada pela base para conferência manual (`review_status`, `review_notes`) |
| `figures/*.svg` | gráficos de barras sem dependências externas |

## Pré-processamento para PLN

```bash
python preprocess.py              # remove stopwords em text_for_model
python preprocess.py --keep-stopwords
```

Lê `data/processed/noticias.jsonl` e grava `data/processed/noticias_nlp.jsonl`. Os campos
originais são preservados e quatro são acrescentados:

| Campo | Descrição |
|-------|-----------|
| `text_normalized` | título + conteúdo em minúsculas, Unicode NFC, espaços normalizados, acentos preservados |
| `tokens` | palavras (com acentos e hífens) e números, sem pontuação; nada é removido |
| `tokens_without_stopwords` | `tokens` sem as 229 stopwords embutidas |
| `text_for_model` | `tokens_without_stopwords` reunidos em uma string, pronto para TF-IDF/BM25 |

Decisões de pré-processamento:

- **Sem stemming ou lematização automática**: dependem da tarefa e reduziriam a legibilidade
  para NER e sumarização; podem ser aplicados depois sobre `tokens`.
- **Stopwords**: lista de português do NLTK (artigos, preposições, pronomes, formas de
  ser/estar/ter/haver) acrescida de contrações comuns em textos jornalísticos (`nesta`,
  `neste`, `desta`...). Fica embutida no código para a etapa ser reproduzível sem downloads.
  `não` é removido como no NLTK; tarefas sensíveis à negação devem usar `tokens`.
- **Acentos preservados** em todas as representações derivadas (só a chave de deduplicação
  os remove), evitando colisões como `sede`/`sedé` e mantendo a ortografia do português.

## Testes

```bash
pip install -r requirements-dev.txt
pytest -q
```

Os testes usam HTML local e não fazem requisições ao site.

## Resultados da coleta (2026-09-06)

### Por listagem de origem

| Listagem | Páginas | Coletadas | Únicas | Republicações | Curtas (<20 palavras) |
|----------|--------:|----------:|-------:|--------------:|----------------------:|
| `aniversarios` | 5 | 50 | 50 | 0 | 0 |
| `destaques` | 12 | 120 | 106 | 12 | 2 |
| `diversos` | 8 | 80 | 64 | 3 | 13 |
| `esportes` | 10 | 100 | 99 | 1 | 0 |
| `eventos` | 15 | 150 | 101 | 43 | 6 |
| `falecidos` | 5 | 50 | 48 | 0 | 2 |
| `geral` | 2 | 23 | 21 | 2 | 0 |
| `noticias` | 12 | 120 | 120 | 0 | 0 |
| `ocorrencias` | 15 | 150 | 148 | 0 | 2 |
| `saude` | 10 | 100 | 50 | 42 | 8 |
| `tempo` | 12 | 120 | 116 | 2 | 2 |
| `transito` | 10 | 100 | 80 | 20 | 0 |
| **Total (antes de unir por URL)** | **116** | **1163** | **1003** | **125** | **35** |

### Base consolidada

| Indicador | Valor |
|-----------|------:|
| Registros brutos (URLs distintas após unir as listagens) | 1140 |
| Republicações removidas (mesmo hash de título+conteúdo) | 133 |
| Textos curtos removidos (<20 palavras) | 35 |
| **Notícias na base processada** | **977** |
| Período de publicação | 2025-09-12 a 2026-09-06 |
| Palavras por notícia (mín / mediana / média / máx) | 21 / 201 / 240.36 / 1621 |
| Vocabulário (tokens distintos sem stopwords e números) | 15362 |
| Campos ausentes na base processada | title: 0, published_at: 0, category: 0, content: 0, url: 0 |
| Datas inválidas | 0 |

### Distribuição por categoria declarada (base processada)

| Categoria | Notícias | % |
|-----------|---------:|--:|
| Ocorrências | 148 | 15.1% |
| Notícias | 119 | 12.2% |
| Tempo | 115 | 11.8% |
| Destaques | 106 | 10.8% |
| Esportes | 99 | 10.1% |
| Eventos | 84 | 8.6% |
| Trânsito | 79 | 8.1% |
| Diversos | 62 | 6.3% |
| Aniversários | 50 | 5.1% |
| Saúde | 50 | 5.1% |
| Falecidos | 48 | 4.9% |
| Oktoberfest | 13 | 1.3% |
| Diversos, Uncategorized | 1 | 0.1% |
| Notícias, Uncategorized | 1 | 0.1% |
| Tempo, Uncategorized | 1 | 0.1% |
| Oktoberfest, Trânsito | 1 | 0.1% |

### Notícias por mês de publicação

| Mês | Notícias |
|-----|---------:|
| 2025-09 | 8 |
| 2025-10 | 8 |
| 2025-11 | 8 |
| 2025-12 | 8 |
| 2026-01 | 7 |
| 2026-02 | 10 |
| 2026-03 | 13 |
| 2026-04 | 18 |
| 2026-05 | 84 |
| 2026-06 | 104 |
| 2026-07 | 178 |
| 2026-08 | 441 |
| 2026-09 | 90 |

### Listagem de origem × categoria declarada

Uma notícia pode estar em mais de uma categoria; o campo `category` guarda a primeira do JSON-LD.

| Listagem | Categorias declaradas encontradas |
|----------|-----------------------------------|
| `aniversarios` | Aniversários (50) |
| `destaques` | Destaques (120) |
| `diversos` | Diversos (79) · Diversos, Uncategorized (1) |
| `esportes` | Esportes (100) |
| `eventos` | Eventos (126) · Oktoberfest (24) |
| `falecidos` | Falecidos (50) |
| `geral` | Destaques (4) · Eventos (4) · Diversos (4) · Ocorrências (3) · Notícias (2) · Aniversários (2) · Saúde (2) · Falecidos (1) · Tempo (1) |
| `noticias` | Notícias (119) · Notícias, Uncategorized (1) |
| `ocorrencias` | Ocorrências (150) |
| `saude` | Saúde (100) |
| `tempo` | Tempo (119) · Tempo, Uncategorized (1) |
| `transito` | Trânsito (99) · Oktoberfest, Trânsito (1) |

### Termos mais frequentes (sem stopwords e números)

| Escopo | 12 termos mais frequentes |
|--------|---------------------------|
| geral | blumenau, dia, anos, rua, fonte, ºc, conduzido, masculino, sc, local, tempo, chuva |
| Destaques | blumenau, dia, prefeitura, saúde, setembro, município, rua, gaspar, atendimento, serviços, sobre, fonte |
| Ocorrências | anos, blumenau, conduzido, masculino, rua, envolvendo, dia, sofreu, local, solo, bombeiros, sc |
| Tempo | ºc, máxima, tempo, chuva, dia, vento, sol, fraco, oeste, frio, mínima, leste |
| Esportes | blumenau, atletas, competição, equipe, dia, sub, campeonato, medalhas, bronze, estadual, ouro, etapa |
| Eventos | dia, blumenau, evento, programação, agosto, sábado, local, música, cultura, público, edição, setembro |
| Notícias | blumenau, homem, polícia, anos, militar, pm, bairro, fonte, policiais, imagem, preso, drogas |
| Diversos | dia, blumenau, rua, blogdojaime, fonte, projeto, santa, municipal, missa, programa, sobre, educação |
| Trânsito | rua, trânsito, br, blumenau, obras, dia, partir, fonte, dnit, ponte, sc, motoristas |
| Saúde | saúde, vacinação, unidades, dia, família, velha, itoupava, blumenau, agf, garcia, rua, contra |
| Aniversários | dia, hoje, aniversário, blumenau, jaime, pessoa, aniversariantes, desejamos, todos, seguidores, citados, muitas |
| Oktoberfest | oktoberfest, blumenau, festa, oficial, cultura, evento, cerveja, edição, santa, catarina, spaten, outubro |
| Falecidos | funerária, maria, falecidos, últimas, atualizado, dia, sentimentos, familiares, amigos, fonte, central, blumenau |
| Oktoberfest, Trânsito | rua, blumenau, joão, pessoa, humberto, campos, vila, germânica, oktoberfest, oficial, cultura, trânsito |
| Diversos, Uncategorized | contribuintes, restituição, prioridade, declaração, receita, renda, legal, lotes, consulta, imposto, restituições, contribuinte |
| Notícias, Uncategorized | blumenau, prisão, mulher, homem, polícia, mandado, justiça, artigo, dirigir, pm, militar, preventivo |
| Tempo, Uncategorized | tempo, ºc, máxima, chuva, blumenau, sobre, vento, fraco, fraca, terça-feira, partir, quarta-feira |

### Leitura dos resultados

- **Diversidade de categorias**: as 11 categorias do portal estão representadas, com pesos
  entre 48 (Falecidos) e 148 (Ocorrências) notícias. Além delas aparecem a sub-categoria
  `Oktoberfest` (13 + 1 combinada com Trânsito) e três rótulos compostos com `Uncategorized`,
  todos herdados do `articleSection` do portal. Para classificação supervisionada, recomenda-se
  normalizar esses rótulos (ficar com a primeira categoria antes da vírgula e mapear
  `Oktoberfest` para `Eventos`), o que deixa 11 classes.
- **Republicações**: a taxa de duplicatas varia muito por categoria. Saúde (42 de 100) e
  Eventos (43 de 150) republicam a mesma nota de serviço em dias seguidos (horários de
  ambulatórios, programação de festas); Ocorrências e Notícias praticamente não repetem.
  Sem a deduplicação por conteúdo, 12% da base seria texto repetido.
- **Textos curtos** (35): são posts cujo conteúdo é só uma imagem ou um vídeo embutido
  (mensagens em vídeo, cartazes de horários). O HTML foi inspecionado manualmente: o container
  de conteúdo existe, mas não tem parágrafos, então não é falha do parser.
- **Distribuição temporal**: a coleta pega as páginas mais recentes de cada categoria, por isso
  há concentração em agosto de 2026 (441 notícias). Categorias com menor frequência de
  publicação (Saúde, Trânsito) alcançam meses mais antigos, chegando a setembro de 2025.
- **Listagem geral × categorias**: as duas páginas reais de `/noticias/` trouxeram notícias de
  9 categorias diferentes, confirmando que ela é diversa, porém rasa; as páginas de categoria
  entregam a profundidade.
- **Assinaturas lexicais**: os termos mais frequentes por categoria mostram gêneros textuais
  distintos. Ocorrências segue o modelo de boletim (`conduzido`, `masculino`, `sofreu`,
  `bombeiros`); Tempo é quase numérico (`ºc`, `máxima`, `mínima`, `vento`); Falecidos e
  Aniversários são formulaicos (quase todos os termos aparecem exatamente uma vez por notícia,
  contagens 47–50), o que os torna triviais para classificação e pouco úteis para sumarização.
  `blumenau` é o termo mais frequente da base (2.598 ocorrências) e `fonte` aparece por causa
  dos créditos ao final das notícias ("Fonte: Polícia Militar").
- **Pré-processamento**: em média cada notícia tem 264 tokens, reduzidos a 169 após as
  stopwords (redução de 36%). O vocabulário sem stopwords e números tem 15.362 formas.
  Termos genéricos como `dia`, `anos`, `rua`, `fonte` e `sobre` sobrevivem à lista e são
  candidatos a uma lista de stopwords de domínio em etapas futuras.

### Revisão manual da amostra

`reports/review_sample.csv` traz 20 notícias espalhadas por todo o período (setembro de 2025 a
setembro de 2026) e por 9 categorias. Cada uma foi comparada com a página original no portal:
título (`<h1>`), data (`datePublished` do JSON-LD), categoria (`articleSection`) e conteúdo
(parágrafos do container da notícia), além de uma verificação de que textos de rodapé e barra
lateral do portal não vazaram para o conteúdo.

| Resultado | Notícias |
|-----------|---------:|
| Título, data e categoria corretos | 20 / 20 |
| Conteúdo correto na primeira checagem automática por parágrafos | 15 / 20 |
| Conteúdo correto após corrigir a checagem e reconferir | 20 / 20 (100% dos parágrafos) |
| Vazamento de rodapé/barra lateral | 0 / 20 |

As cinco notícias apontadas na primeira passagem (um boletim policial, duas previsões do tempo,
um cumprimento de mandado e um obituário) eram falsos positivos do script de comparação: ele
extraía o texto da página sem separador de espaço, colando palavras em torno de `<br>` e de
tags inline (datas e nomes em negrito), o que impedia a busca por substring. Duas verificações
independentes confirmaram a coleta: o parser do projeto aplicado à página ao vivo produz texto
idêntico ao armazenado, e o script corrigido encontrou todos os parágrafos das 20 notícias.
As colunas `review_status` e `review_notes` do CSV registram o resultado final por notícia.
A revisão está preservada em `reports/review_sample.revisado.csv`, porque `analyze.py` regrava
`review_sample.csv` em branco a cada execução.

## Limitações conhecidas

1. **Amostra, não acervo**: o portal tem ~49 mil posts; a base cobre as páginas mais recentes
   de cada categoria (116 páginas de listagem). Coletas futuras com `collect.sh` ampliam a
   profundidade de forma incremental.
2. **Viés de recência e de categoria**: o volume por mês reflete a ordem de coleta, não a
   produção do portal; a proporção entre categorias reflete o número de páginas escolhido por
   categoria, não a frequência real de publicação.
3. **Rótulo único para notícias multi-rótulo**: `category` guarda a primeira categoria do
   JSON-LD. A proveniência por listagem (`reports/listing_vs_category.csv`) mostra que a
   discordância é pequena, mas existe (ex.: notícias da listagem Eventos rotuladas Oktoberfest).
4. **Deduplicação exata**: detecta republicações idênticas, mas não *quase-duplicatas*
   (boletins diários de acidentes e previsões do tempo com números diferentes). Um passo de
   similaridade (TF-IDF + cosseno ou MinHash) é o próximo filtro natural.
5. **Categorias formulaicas**: Falecidos e Aniversários são listas de nomes; foram mantidas
   com poucas páginas para representar o portal, mas devem ser excluídas de tarefas como
   sumarização ou NER de pessoas (expõem nomes de cidadãos comuns).
6. **Dependência do layout**: o parser foi ajustado ao tema Elementor atual do portal; uma
   mudança de tema exige atualizar os seletores (os testes com HTML local ajudam a detectar).
7. **Pré-processamento leve**: sem lematização, sem tratamento de entidades compostas
   (`Vila Itoupava`, `BR-470`) e com `não` removido; tarefas que dependem disso devem partir
   de `content` ou `tokens`.
8. **Carga sobre o portal**: páginas de arquivo são lentas (5 s ou mais) e o portal oscila;
   a coleta completa levou ~1h40 com dois lotes. Não reduzir `--delay` nem aumentar o paralelismo.

## Próximos usos da base

| Tarefa | Entrada sugerida | Caminho inicial |
|--------|------------------|-----------------|
| Classificação de texto | `text_for_model` + `category` normalizada (11 classes) | TF-IDF + Regressão Logística como baseline; depois BERTimbau. Atenção ao desbalanceamento (48 a 148 por classe). |
| Extração de informações (NER) | `content` (caixa e pontuação originais) | spaCy `pt_core_news_lg` + regras para bairros (Garcia, Velha, Itoupava), rodovias (BR-470, SC-108) e órgãos (PM, Bombeiros, DNIT). |
| Recuperação de informações | `text_for_model` para BM25; `content` para embeddings | Índice BM25 com filtros por `category` e `published_at`; reranking por embeddings multilíngues. |
| Sumarização e agrupamento | `content`, `content_hash`, `published_at` | Agrupar boletins diários (acidentes, tempo) por similaridade e gerar resumos por período. |
| Chatbot com fontes | resultado da recuperação + `url` | RAG: recuperar as notícias relevantes e responder citando `title`, `published_at` e `url`, sem inventar informações. |

## Reprodução completa

```bash
./collect.sh                                                    # ou dois lotes em paralelo
python merge_raw.py data/raw/parts/*.jsonl --minimum-words 20
python analyze.py --minimum-words 20 --sample-size 20 --top-terms 30
python preprocess.py
pytest -q
```

Os diretórios `data/` e `reports/` estão no `.gitignore`; para compartilhar a base coletada,
remova essas regras ou distribua os arquivos separadamente.
