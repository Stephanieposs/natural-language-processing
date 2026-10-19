# Noticias de Blumenau - projeto de PLN

Projeto de PLN para coletar e organizar noticias publicas de Blumenau e regiao
do Blog do Jaime. Cada registro preserva titulo, conteudo, categoria, data e
URL, formando uma base atualizavel e rastreavel para limpeza textual, analise
exploratoria, agrupamento, busca e classificacao. O corpus reune assuntos locais
variados e desafios reais, como noticias relacionadas ao mesmo acontecimento e
nomes de bairros e instituicoes. `projeto_pln.py` orquestra o fluxo; as
representacoes e tarefas de PLN ficam em modulos separados.

## Instalacao

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m nltk.downloader punkt punkt_tab stopwords rslp
python -m spacy download pt_core_news_sm
```

As dependencias estao em `requirements.txt`. Na primeira indexacao BERT, o
modelo pre-treinado e baixado para o cache local; essa etapa exige internet e
pode demorar, mas as buscas seguintes reutilizam os embeddings salvos.

## Execucao

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

Consulta as 10 paginas mais recentes, atualiza URLs ja conhecidas, acrescenta
URLs novas, remove duplicatas de conteudo e regenera os dados de PLN e relatorios.

### Agendamento diario opcional

```powershell
python projeto_pln.py --agendar-diariamente
```

Cria a tarefa `ProjetoPLNNoticiasBlumenau`, que executa `--atualizar` todos os
dias as 22:00. Para remove-la:

```powershell
schtasks /Delete /TN "ProjetoPLNNoticiasBlumenau" /F
```

### Regerar somente vetores e clusters

```powershell
python projeto_pln.py --agrupar
```

Usa `data/processed/noticias_nlp.jsonl`, sem acessar o portal.

As etapas tambem podem ser executadas separadamente:

```powershell
python bag_of_words.py
python tf_idf.py
python clustering.py
python word2vec.py
python bert.py
python classificacao.py
```

`clustering.py` tambem regenera Bag of Words e TF-IDF, mantendo matrizes,
vocabulario e clusters na mesma versao da base.

Para comparar a clusterizacao entre BoW, TF-IDF, Word2Vec e BERT:

```powershell
python projeto_pln.py --comparar-clusters
```

O comando testa `k=9`, `k=12` e `k=13`, salvando silhouette, pureza por
categoria e distancias entre centroides em
`reports/cluster_representations_comparison.csv`.

Para gerar a visualizacao PCA da melhor combinacao observada na comparacao
atual, Word2Vec com `k=12`:

```powershell
python projeto_pln.py --visualizar-word2vec-clusters
```

O comando salva `reports/clusters_word2vec_k12.html` e
`reports/clusters_word2vec_k12_3d.html`, sem substituir as visualizacoes TF-IDF.

Para completar PCA e visualizacoes de BoW e BERT:

```powershell
python projeto_pln.py --visualizar-clusters bow bert --numero-clusters 13
```

O comando reutiliza `bow_matrix.csv` e `embeddings_bert.csv`, valida a versao
da base e a ordem dos documentos e executa K-Means com `random_state=42` e
`n_init=10`. O valor `k=13` foi o melhor testado para cada uma dessas duas
representacoes na comparacao salva; Word2Vec com `k=12` continua sendo a melhor
combinacao geral observada. O agrupamento usa os vetores completos; PCA serve
somente para visualizacao.

Para cada representacao, sao gerados:

- `reports/clusters_bow_k13.html` e `clusters_bow_k13_3d.html` (ou `bert`):
  graficos interativos em 2D e 3D;
- `data/processed/noticias_clusters_bow_k13.jsonl` (ou `bert`): grupos,
  categoria majoritaria e coordenadas PCA por noticia;
- `data/processed/modelo_kmeans_bow_k13.joblib` (ou `bert`): modelo persistido;
- `reports/cluster_summary_bow_k13.csv` (ou `bert`): tamanho, pureza e coesao
  por grupo;
- `reports/cluster_centroid_distances_bow_k13.csv` (ou `bert`): distancias
  de cosseno entre centroides;
- `reports/cluster_visualization_bow_k13.json` (ou `bert`): parametros,
  identificador da base, silhouette e variancia explicada pelo PCA.

E possivel gerar apenas uma representacao, por exemplo
`python projeto_pln.py --visualizar-clusters bert --numero-clusters 13`.

### Criar os indices de busca

```powershell
python projeto_pln.py --indexar-busca
```

Treina Word2Vec na base local e gera embeddings BERT para todas as noticias. O
processo nao faz parte da atualizacao diaria porque o modelo BERT e maior e sua
indexacao e mais demorada. Para criar apenas Word2Vec, sem baixar ou executar
BERT:

```powershell
python projeto_pln.py --indexar-busca --sem-bert
```

### Pesquisar noticias

```powershell
python projeto_pln.py --buscar "acidente no centro de Blumenau" --metodo tfidf --metrica cosseno --top-k 10
```

As representacoes disponiveis sao `bow`, `tfidf`, `word2vec` e `bert`. As metricas
disponiveis sao `cosseno`, `euclidiana` e `manhattan`. Para as duas distancias,
o programa usa `1 / (1 + distancia)`, mantendo valores maiores para resultados
mais proximos.

### Comparar representacoes e metricas

```powershell
python projeto_pln.py --comparar-buscas "acidente no centro de Blumenau" --top-k 3
```

O comando testa as doze combinacoes entre as quatro representacoes e as tres
metricas. O resultado completo fica em `reports/comparacao_buscas.csv`, com
titulo, categoria, URL e score de cada posicao.

Para gerar uma avaliacao top-3/top-5 em consultas padrao:

```powershell
python projeto_pln.py --avaliar-buscas
```

O resultado fica em `reports/busca_topk_avaliacao.csv`, com score medio,
categoria dominante, proporcao da categoria dominante e titulos retornados por
representacao.

### Classificar as categorias

```powershell
python projeto_pln.py --classificar
```

Segue o fluxo: titulo e conteudo -> representacao textual -> Regressao
Logistica -> categoria prevista. O comando separa treino e teste de forma
estratificada e compara BoW, TF-IDF, Word2Vec e BERT. Para que cada classe tenha
uma amostra minima no teste, categorias com menos de 30 noticias nao entram no
treinamento.

### Extrair entidades nomeadas e relacoes

```powershell
python projeto_pln.py --extrair-relacoes
```

Usa spaCy com `pt_core_news_sm` para localizar entidades nomeadas no titulo e
conteudo das noticias. Em seguida, aplica regras sobre dependencias sintaticas
para extrair triplas do tipo sujeito -> relacao -> objeto/complemento. As
relacoes usam o lema do verbo e, quando o complemento e preposicionado, incluem
a preposicao normalizada, como `trabalhar_em` ou `colaborar_com`.
Tanto o NER quanto as relacoes sao preditivos e aproximados: as entidades
dependem dos rotulos do modelo spaCy e podem ter fronteiras ou categorias
incorretas; as relacoes dependem do parser sintatico e de regras locais.

### Analisar sentimentos

```powershell
python projeto_pln.py --sentimentos
```

Classifica cada noticia como `positivo`, `neutro` ou `negativo` usando um
lexico em portugues com tratamento simples de negacao, intensidade e expressoes
curtas. A abordagem e auditavel: cada linha guarda os termos positivos e
negativos que influenciaram a pontuacao. Como noticias locais tendem a usar
linguagem informativa, o resultado deve ser interpretado como polaridade lexical
do texto, nao como emocao real dos envolvidos.

## Fluxo dos dados

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
data/processed/noticias.jsonl
             |
             v
Tokenizacao, normalizacao, stopwords, lematizacao e stemming
             |
             v
data/processed/noticias_nlp.jsonl
             |
             v
Recorte dos ultimos 7 dias e comparacao com o periodo anterior
             |
             v
Bag of Words e TF-IDF -> K-Means -> PCA em duas e tres dimensoes
             |
             v
Relatorios, modelos e visualizacoes dos clusters
             |
             v
Word2Vec + embeddings BERTimbau
             |
             v
Busca com cosseno, distancia euclidiana ou Manhattan
```

### Organizacao dos scripts

| Arquivo | Responsabilidade |
|---|---|
| `projeto_pln.py` | Coleta, limpeza, pre-processamento, comparacao temporal e orquestracao |
| `representacao_textual.py` | Preparacao do corpus e parametros compartilhados pelos vetorizadores |
| `bag_of_words.py` | Vetorizador e matriz Bag of Words |
| `tf_idf.py` | Vetorizador e matriz TF-IDF |
| `clustering.py` | K-Means, PCA, termos dos grupos e persistencia |
| `visualizacao_clusters.py` | Grafico Plotly interativo dos clusters |
| `word2vec.py` | Treinamento, embeddings e pontuacao Word2Vec |
| `bert.py` | BERTimbau, blocos de texto, mean pooling, embeddings e pontuacao |
| `busca.py` | Indexacao e busca com TF-IDF, Word2Vec ou BERTimbau |
| `metricas_busca.py` | Cosseno, distancia euclidiana e Manhattan |
| `comparacao_buscas.py` | Matriz comparativa das representacoes e metricas |
| `classificacao.py` | TF-IDF e Regressao Logistica para prever categorias |
| `entidades_relacoes.py` | NER, triplas sujeito-relacao-objeto e resumos |
| `analise_sentimentos.py` | Polaridade lexical das noticias e resumos por categoria/cluster |

## Camadas da base

### Base bruta

Arquivo: `data/raw/noticias.jsonl`.

Contem o historico coletado antes dos filtros de tamanho e duplicacao por conteudo. Na atualizacao incremental, URLs novas sao acrescentadas e URLs ja conhecidas sao substituidas pela versao mais recente.

### Base limpa

Arquivo: `data/processed/noticias.jsonl`.

Contem somente noticias com pelo menos 20 palavras e sem repeticao de conteudo.
O titulo e o conteudo originais sao preservados.

### Base preparada para PLN

Arquivo: `data/processed/noticias_nlp.jsonl`.

Contem as mesmas noticias da base limpa, acrescidas das representacoes geradas
durante o pre-processamento de PLN.

`noticias` e `noticias_nlp` nao sao copias desnecessarias: a primeira mostra o
resultado da limpeza antes do PLN, enquanto a segunda permite comparar o texto
original com tokens, lemas e stems.

### Base agrupada e vetores

Arquivos:

- `data/processed/bow_matrix.csv` e `tfidf_matrix.csv`: matrizes tabulares com
  uma noticia por linha, `id` na primeira coluna e um termo por coluna;
- `data/processed/vectorizer_bow.joblib` e `vectorizer_tfidf.joblib`: vocabulario
  e configuracao necessarios para transformar novos textos;
- `data/processed/modelo_kmeans.joblib`: modelo de agrupamento escolhido;
- `data/processed/noticias_clusters.jsonl`: noticias com numero, rotulo e
  coordenadas PCA em duas e tres dimensoes, categoria real normalizada e
  categoria atribuida pelo cluster;
- `data/processed/similaridade_bow.csv` e `similaridade_tfidf.csv`: matrizes
  de similaridade do cosseno entre todas as noticias.

### Entidades e relacoes

Arquivos:

- `data/processed/noticias_entidades.jsonl`: mencoes reconhecidas pelo NER,
  com noticia, sentenca, texto da entidade, rotulo e posicoes de caracteres;
- `data/processed/noticias_relacoes.csv`: triplas extraidas com sujeito,
  relacao, objeto, sentenca de origem, verbo e dependencia sintatica do objeto;
- `reports/entities_summary.csv`: quantidade de mencoes e entidades distintas
  por rotulo do spaCy;
- `reports/relations_summary.csv`: relacoes mais frequentes e pares principais.

A extracao de relacoes e baseada em regras, portanto deve ser lida como uma
aproximacao auditavel. Ela cobre sujeitos ligados ao mesmo verbo e complementos
`obj`, `iobj` e `obl`; tambem reaproveita o sujeito de verbos coordenados em
alguns casos. Nao resolve correferencia, sinonimia, negacao, tempo verbal ou
papeis semanticos completos.

### Sentimentos

Arquivos:

- `data/processed/noticias_sentimentos.jsonl`: pontuacao e rotulo de sentimento
  por noticia, com evidencias lexicais positivas e negativas;
- `reports/sentiment_summary.csv`: totais gerais e media de polaridade;
- `reports/sentiment_by_category.csv`: distribuicao de sentimentos por
  categoria original normalizada;
- `reports/sentiment_by_cluster.csv`: distribuicao de sentimentos por cluster,
  quando os clusters estao atualizados.

A pontuacao varia de -1 a 1: valores negativos indicam predominancia de termos
negativos, valores positivos indicam predominancia de termos positivos e valores
proximos de zero ficam como `neutro`. O metodo usa lexico local e regras simples,
portanto e transparente, mas nao substitui um classificador supervisionado
treinado com exemplos anotados de sentimentos.

O corpus usa diretamente `tokens_sem_stopwords`. O K-Means usa
`NUMERO_CLUSTERS = 12`, como teste proximo da quantidade de categorias
normalizadas usadas pelo Blog do Jaime na base coletada. O PCA gera tres
coordenadas usadas somente nas
visualizacoes 2D e 3D. Para comparar o agrupamento nao supervisionado com as
categorias originais, cada cluster recebe a categoria majoritaria das noticias
que cairam nele, e essa atribuicao alimenta a matriz de confusao.

### Indices de busca

Arquivos:

- `data/processed/modelo_word2vec.model`: vocabulario e pesos Word2Vec;
- `data/processed/embeddings_word2vec.csv`: uma linha por noticia e 190
  dimensoes Word2Vec (`w2v_000`, `w2v_001`, ...);
- `data/processed/embeddings_bert.csv`: uma linha por noticia e 768 dimensoes
  BERTimbau (`bert_000`, `bert_001`, ...);
- `data/processed/indice_busca.json`: modelo, dimensoes e identificador da base
  usada na indexacao.

Os vetores Word2Vec sao a media simples dos vetores das palavras conhecidas. O
BERTimbau utiliza titulo e conteudo originais. Textos longos sao divididos em
blocos de 256 tokens do modelo; o embedding final e a media dos embeddings dos
blocos, para que o final da noticia tambem participe da busca.

## Limpeza e preparacao

O HTML perde tags de ruído, espacos repetidos, textos curtos e duplicatas. O
NLTK gera `tokens`, normaliza com `casefold()` e remove pontuacao, numeros e
stopwords, produzindo `tokens_sem_stopwords`. A partir deles, spaCy gera lemas
e o `RSLPStemmer` gera radicais em colunas separadas.

## Recortes temporais adicionais

Como comparacao adicional, a base de PLN e dividida em dois recortes:

- noticias dos sete dias mais recentes em relacao a data mais nova da base;
- noticias anteriores a esse periodo.

O programa compara quantidade de noticias, periodo, media de palavras,
categorias e termos mais frequentes. O resultado fica consolidado em
`reports/summary.json`, sem criar quatro copias adicionais da base.

## Formatos

- JSONL armazena uma noticia por linha e preserva listas como `tokens`, `lemas`
  e `stems`;
- CSV armazena as matrizes Bag of Words, TF-IDF, similaridades e embeddings;
- Joblib preserva vetorizadores e modelos; CSV armazena matrizes e embeddings.

## Relatorios

- `reports/summary.json`: modo da execucao, paginas consultadas, noticias novas
  e atualizadas, totais, datas, categorias, comparacao temporal, vetorizacao e
  valores de silhouette;
- `reports/cluster_summary.csv`: tamanho, rotulo, termos e coesao media de
  cada cluster, alem da categoria majoritaria e pureza por categoria;
- `reports/cluster_category_matrix.csv`: contagem de categorias reais por
  cluster numerico;
- `reports/cluster_category_mapping.csv`: categoria majoritaria atribuida a
  cada cluster;
- `reports/cluster_confusion_matrix.csv`: matriz de confusao entre categoria
  real e categoria atribuida pelo cluster;
- `reports/cluster_centroid_distances.csv`: distancia entre os centroides dos
  clusters;
- `reports/cluster_representations_comparison.csv`: silhouette, pureza por
  categoria e distancias entre centroides para BoW, TF-IDF, Word2Vec e BERT;
- `reports/clusters_tfidf.html` e `reports/clusters_tfidf_3d.html`: graficos
  interativos PCA em duas e tres dimensoes;
- `reports/clusters_word2vec_k12.html` e `clusters_word2vec_k12_3d.html`:
  graficos interativos PCA dos clusters Word2Vec com `k=12`;
- `reports/classification_report.csv`: precision, recall, F1 e suporte por
  categoria no conjunto de teste;
- `reports/classification_comparison.csv`: acuracia, macro-F1 e weighted-F1 por
  representacao textual;
- `reports/entities_summary.csv`: contagens de entidades por rotulo;
- `reports/relations_summary.csv`: contagens de relacoes extraidas;
- `reports/sentiment_summary.csv`, `sentiment_by_category.csv` e
  `sentiment_by_cluster.csv`: resumos da analise de sentimentos;
- `reports/comparacao_buscas.csv`: ranking comparativo entre representacoes e
  metricas para a consulta informada.
- `reports/busca_topk_avaliacao.csv`: avaliacao top-3/top-5 das consultas de
  busca por representacao.

Todos os relatorios sao regenerados depois da coleta inicial ou de uma
atualizacao incremental.

## Estado da execucao

Os totais de coleta, qualidade, recorte temporal, vetorizacao e silhouette sao
atualizados a cada execucao em `reports/summary.json`; por isso o README nao
mantem numeros que se tornam defasados com novas noticias.

## Configuracoes

- `INITIAL_PAGES = 50`: paginas usadas na coleta inicial;
- `UPDATE_PAGES = 10`: paginas consultadas nas atualizacoes;
- `DELAY_SECONDS = 1.0`: pausa entre requisicoes;
- `MINIMUM_WORDS = 20`: tamanho minimo de uma noticia valida;
- `RECENT_DAYS = 7`: tamanho do recorte recente;
- `clustering.py`: `NUMERO_CLUSTERS` e `TOP_TERMOS`;
- `representacao_textual.py`: `MAX_VECTOR_FEATURES`, compartilhado por Bag of
  Words e TF-IDF;
- `word2vec.py`: `WORD2VEC_VECTOR_SIZE` e `WORD2VEC_EPOCHS`;
- `bert.py`: `BERT_MODEL_NAME`;
- `TASK_TIME = "22:00"`: horario da atualizacao diaria.
