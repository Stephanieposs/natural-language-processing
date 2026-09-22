# Noticias de Blumenau - projeto de PLN

Projeto tem com objetivo coletar, organizar e preparar noticias locais para
aplicacoes de Processamento de Linguagem Natural (PLN).

Todo o fluxo esta no arquivo `projeto_pln.py`: coleta, atualizacao incremental,
limpeza, analise exploratoria, tokenizacao, normalizacao, remocao de stopwords,
lematizacao, stemming, comparacao temporal e exportacao dos resultados.

## 1. Tema e tipo de dado textual

O trabalho utiliza noticias sobre Blumenau e regiao, coletadas do portal Blog
do Jaime. Cada registro possui titulo, conteudo, categoria, data de publicacao
e link para a fonte original.

O tema e a centralizacao e organizacao automatica de noticias locais. O objetivo
e reunir as publicacoes em uma base estruturada, facilitando a busca, a
classificacao e a consulta de informacoes relevantes sobre Blumenau.

## 2. Justificativa da escolha

O Blog do Jaime foi escolhido por sua relevancia para Blumenau. O portal e
consultado pela populacao para acompanhar acontecimentos locais, recebe novas
publicacoes frequentemente e possui grande quantidade de noticias sobre temas
variados.

As publicacoes sao publicas e apresentam uma estrutura que permite coletar
titulo, texto, categoria, data e URL por web scraping. A presenca de assuntos
como ocorrencias, transito, eventos, saude, esportes, previsao do tempo e
informacoes da cidade torna a fonte adequada para formar uma base textual local
e heterogenea.

## 3. Adequacao da base para PLN

A base e adequada para experimentos de PLN pelos seguintes motivos:

- volume: centenas de noticias sao obtidas a partir de 50 paginas;
- abrangencia: as publicacoes cobrem diferentes acontecimentos de Blumenau e
  regiao;
- variedade: a base atual possui diferentes rotulos de categoria e textos com
  tamanhos variados;
- atualidade: a fonte recebe novas noticias continuamente;
- rastreabilidade: cada texto preserva a data e a URL original;
- estrutura: titulo, conteudo e categoria permitem criar entradas e rotulos
  para diferentes tarefas de PLN.

Os textos tambem apresentam desafios reais, como noticias sobre mais de um
assunto, atualizacoes do mesmo acontecimento, nomes especificos de bairros e
instituicoes e diferentes formas de escrever uma mesma consulta.

## 4. Possiveis aplicacoes

| Tarefa | Entrada | Processo | Saida esperada |
|---|---|---|---|
| Classificacao de texto | Titulo e conteudo | TF-IDF com Regressao Logistica ou modelo baseado em BERT | Categoria como seguranca, transito, eventos, saude, esportes ou tempo |
| Extracao de informacoes | Titulo e conteudo | NER e regras de extracao | Pessoas, locais, bairros, datas, horarios, instituicoes e eventos |
| Recuperacao de informacoes | Consulta do usuario em linguagem natural | Palavras-chave, BM25 ou embeddings, com filtros por categoria, local e periodo | Noticias ordenadas por relevancia, com titulo, data e link |
| Chatbot ou agente | Pergunta do usuario | Recuperacao das noticias relacionadas e geracao fundamentada nos textos | Resposta acompanhada das fontes, sem inventar informacoes |
| Sumarizacao e agrupamento | Conjunto de noticias | Sumarizacao, similaridade textual e agrupamento por topicos | Resumos, assuntos recorrentes e grupos sobre o mesmo acontecimento |

O projeto atual prepara a base para essas aplicacoes. O treinamento e a
avaliacao de modelos especificos podem ser desenvolvidos em etapas posteriores.

## 5. Dificuldades e estrategias adotadas

| Dificuldade | Estrategia no projeto |
|---|---|
| Mudancas ou variacoes no HTML | Uso de seletores alternativos e leitura dos metadados JSON-LD |
| Falhas temporarias de rede | Ate tres tentativas por requisicao e registro das paginas que falharam |
| Interrupcao durante uma coleta longa | Salvamento da base bruta ao final de cada pagina |
| Noticias repetidas | Comparacao por URL e hash normalizado do titulo e conteudo |
| Textos vazios ou muito curtos | Remocao de noticias com menos de 20 palavras |
| Noticia com a mesma URL atualizada | Substituicao do registro anterior pela versao mais recente |
| Categorias e assuntos variados | Preservacao da categoria original e geracao de distribuicoes |
| Entidades locais desconhecidas por modelos genericos | Preservacao do texto e da fonte para futura adaptacao de NER |
| Consultas com palavras diferentes das noticias | Base preparada para futura busca semantica com embeddings |
| Resumos ou respostas incorretas | URLs originais mantidas para fundamentacao e conferencia |

## 6. Instalacao

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m nltk.downloader punkt punkt_tab stopwords rslp
python -m spacy download pt_core_news_sm
```

Bibliotecas utilizadas:

- Requests: acesso as paginas;
- Beautiful Soup: leitura e limpeza do HTML;
- Pandas: organizacao e exportacao dos dados;
- NLTK: tokenizacao, stopwords e stemming;
- spaCy: lematizacao em portugues.

## 7. Formas de execucao

### Coleta inicial

```powershell
python projeto_pln.py
```

Coleta as 50 paginas mais recentes e cria uma nova base. Esse modo deve ser
usado na primeira execucao ou quando for necessario reconstruir toda a base.

### Atualizacao incremental

```powershell
python projeto_pln.py --atualizar
```

Consulta somente as 10 paginas mais recentes e combina o resultado com o
historico existente:

- URLs novas sao acrescentadas;
- URLs existentes sao atualizadas com o conteudo mais recente;
- nenhuma URL e armazenada duas vezes;
- duplicatas de conteudo continuam sendo removidas da base limpa;
- dados de PLN e relatorios sao regenerados.

### Agendamento diario opcional

```powershell
python projeto_pln.py --agendar-diariamente
```

Esse comando cria a tarefa `ProjetoPLNNoticiasBlumenau` no Agendador de Tarefas
do Windows. Ela executa `--atualizar` diariamente as 22:00 e consulta somente
as 10 paginas mais recentes.

O agendamento esta implementado, mas nao fica ativo apenas por existir no
codigo. Ele so e instalado quando o comando acima e executado. Para remover uma
tarefa ja instalada:

```powershell
schtasks /Delete /TN "ProjetoPLNNoticiasBlumenau" /F
```

## 8. Fluxo dos dados

```text
Coleta inicial: 50 paginas
Atualizacao diaria: 10 paginas
             |
             v
Mesclagem por URL e atualizacao de noticias existentes
             |
             v
data/raw/noticias.jsonl
             |
             v
Remocao de duplicatas de conteudo e textos curtos
             |
             v
data/processed/noticias.jsonl e noticias.csv
             |
             v
Tokenizacao, normalizacao, stopwords, lematizacao e stemming
             |
             v
data/processed/noticias_nlp.jsonl e noticias_nlp.csv
             |
             v
Recorte dos ultimos 7 dias e comparacao com o periodo anterior
```

## 9. Camadas da base

### Base bruta

Arquivo: `data/raw/noticias.jsonl`.

Contem o historico coletado antes dos filtros de tamanho e duplicacao por
conteudo. Na atualizacao incremental, URLs novas sao acrescentadas e URLs ja
conhecidas sao substituidas pela versao mais recente.

### Base limpa

Arquivos:

- `data/processed/noticias.jsonl`;
- `data/processed/noticias.csv`.

Contem somente noticias com pelo menos 20 palavras e sem repeticao de conteudo.
O titulo e o conteudo originais sao preservados.

### Base preparada para PLN

Arquivos:

- `data/processed/noticias_nlp.jsonl`;
- `data/processed/noticias_nlp.csv`.

Contem as mesmas noticias da base limpa, acrescidas das representacoes geradas
durante o pre-processamento de PLN.

`noticias` e `noticias_nlp` nao sao copias desnecessarias: a primeira mostra o
resultado da limpeza antes do PLN, enquanto a segunda permite comparar o texto
original com tokens, lemas e stems.

## 10. Dicionario de dados

| Campo | Tipo | Presente em | Descricao | Exemplo |
|---|---|---|---|---|
| `title` | texto | Todas as bases | Titulo original da noticia | `Evento acontece em Blumenau` |
| `published_at` | data/hora em texto | Todas as bases | Momento de publicacao informado pelo portal | `2026-09-16T10:00:00-03:00` |
| `category` | texto | Todas as bases | Categoria atribuida pelo portal | `Eventos` |
| `content` | texto | Todas as bases | Conteudo original sem as tags HTML | `A programacao inicia...` |
| `url` | texto | Todas as bases | Link original e identificador usado na atualizacao | `https://blogdojaime.com.br/.../` |
| `collected_at` | data/hora em texto | Todas as bases | Momento em que a pagina foi coletada | `2026-09-16T21:00:00+00:00` |
| `content_hash` | texto SHA-256 | Todas as bases | Identificador usado para detectar conteudos repetidos | `a3f1...` |
| `word_count` | inteiro | Todas as bases | Quantidade de palavras no conteudo | `245` |
| `texto_bruto` | texto | Base de PLN | Titulo e conteudo unidos | `Evento acontece... A programacao...` |
| `tokens` | lista de textos | Base de PLN | Resultado da tokenizacao, ainda com pontuacao | `["Evento", "acontece", "."]` |
| `tokens_normalizados` | lista de textos | Base de PLN | Tokens em minusculas e somente alfabeticos | `["evento", "acontece"]` |
| `tokens_sem_stopwords` | lista de textos | Base de PLN | Tokens sem stopwords do portugues | `["evento", "acontece"]` |
| `lemas` | lista de textos | Base de PLN | Formas basicas produzidas pelo spaCy | `["evento", "acontecer"]` |
| `stems` | lista de textos | Base de PLN | Radicais produzidos pelo RSLPStemmer | `["event", "acontec"]` |

Os campos originais nao sao sobrescritos pelas etapas de PLN. Isso permite
auditar e comparar cada transformacao.

## 11. Limpeza e preparacao

### Remocao de ruido

- descarte de tags `script`, `style`, `nav`, `form` e `iframe`;
- conversao do HTML em texto;
- remocao de espacos e quebras de linha repetidos;
- remocao de conteudos duplicados;
- remocao de textos com menos de 20 palavras.

### Tokenizacao

O NLTK divide cada `texto_bruto` em uma lista armazenada em `tokens`.

### Normalizacao e pontuacao

Cada token e convertido para minusculas com `casefold()`. O teste `isalpha()`
mantem apenas tokens alfabeticos, removendo pontuacao e numeros da
representacao normalizada.

### Stopwords

A lista de stopwords em portugues do NLTK remove artigos, preposicoes e outras
palavras muito frequentes. O resultado fica em `tokens_sem_stopwords`.

### Lematizacao e stemming

A lematizacao usa o modelo `pt_core_news_sm` do spaCy. O stemming usa o
`RSLPStemmer` do NLTK. Ambos partem de `tokens_sem_stopwords` e geram colunas
separadas, permitindo comparar as duas tecnicas.

## 12. Recortes temporais adicionais

Como comparacao adicional, a base de PLN e dividida em dois recortes:

- noticias dos sete dias mais recentes em relacao a data mais nova da base;
- noticias anteriores a esse periodo.

Arquivos gerados:

- `data/processed/noticias_recentes_7_dias.jsonl`;
- `data/processed/noticias_recentes_7_dias.csv`;
- `data/processed/noticias_anteriores.jsonl`;
- `data/processed/noticias_anteriores.csv`;
- `reports/temporal_comparison.csv`.

O relatorio compara quantidade de noticias, periodo, media de palavras,
categorias mais frequentes e termos mais frequentes. Esse recorte permite
observar mudancas nos assuntos locais ao longo do tempo sem exigir outra fonte.

## 13. JSONL e CSV

JSONL e CSV apresentam os mesmos registros em formatos diferentes:

- JSONL armazena uma noticia por linha e preserva listas como `tokens`, `lemas`
  e `stems`;
- CSV e mais facil de abrir no Excel ou em outro programa de planilha.

O JSONL e o formato mais adequado para trabalhar com as representacoes de PLN.
O CSV e mantido para consulta e apresentacao tabular.

## 14. Relatorios

- `reports/summary.json`: modo da execucao, paginas consultadas, noticias novas
  e atualizadas, totais, datas, categorias, campos ausentes e estatisticas;
- `reports/category_distribution.csv`: quantidade por categoria;
- `reports/news_by_month.csv`: quantidade por mes;
- `reports/quality_issues.csv`: noticias curtas ou com campos ausentes;
- `reports/review_sample.csv`: amostra de 20 noticias para revisao manual;
- `reports/temporal_comparison.csv`: comparacao entre os dois recortes.

Todos os relatorios sao regenerados depois da coleta inicial ou de uma
atualizacao incremental.

## 15. Resultados das execucoes

### Coleta inicial

A coleta completa de 16/09/2026 apresentou:

- 50 paginas solicitadas e coletadas;
- nenhuma pagina ou noticia com falha;
- 784 noticias brutas;
- 90 duplicatas removidas;
- 43 textos curtos removidos;
- 651 noticias validas e processadas para PLN;
- publicacoes entre 08/08/2026 e 16/09/2026;
- nenhum titulo, data, categoria, conteudo ou URL ausente na base valida.

### Atualizacao incremental atual

A atualizacao pelas 10 paginas mais recentes, realizada em 21/09/2026,
apresentou:

- 10 paginas solicitadas e coletadas;
- nenhuma pagina ou noticia com falha;
- 99 noticias novas;
- 45 URLs existentes atualizadas;
- 883 noticias brutas no historico;
- 101 duplicatas de conteudo removidas;
- 46 textos curtos removidos;
- 736 noticias validas e processadas para PLN;
- 115 noticias no recorte dos sete dias mais recentes;
- 621 noticias no periodo anterior;
- nenhum titulo, data, categoria, conteudo ou URL ausente na base valida.

Os numeros atuais ficam registrados em `reports/summary.json`. Novas
atualizacoes alteram esses valores porque o portal recebe novas publicacoes.

## 16. Configuracoes

- `INITIAL_PAGES = 50`: paginas usadas na coleta inicial;
- `UPDATE_PAGES = 10`: paginas consultadas nas atualizacoes;
- `DELAY_SECONDS = 1.0`: pausa entre requisicoes;
- `MINIMUM_WORDS = 20`: tamanho minimo de uma noticia valida;
- `SAMPLE_SIZE = 20`: tamanho da amostra de revisao;
- `RECENT_DAYS = 7`: tamanho do recorte recente;
- `TASK_TIME = "22:00"`: horario da atualizacao diaria.

