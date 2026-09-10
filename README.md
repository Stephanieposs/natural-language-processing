# Notícias de Blumenau — coleta e preparação para PLN

Trabalho da Etapa Prática 1 de Processamento de Linguagem Natural.

O projeto coleta notícias do [Blog do Jaime](https://blogdojaime.com.br/), portal de Blumenau
e região, organiza tudo numa base única e prepara o texto para tarefas de PLN como
classificação, busca e reconhecimento de entidades.

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python coletar.py     # baixa as notícias do site
python preparar.py    # limpa o texto e gera os campos de PLN
python analisar.py    # estatísticas, gráficos e conferência de qualidade
```

São três programas, na ordem em que devem ser executados:

| Programa | O que faz |
|---|---|
| `coletar.py` | Percorre as categorias do site e salva as notícias em `dados/noticias_coletadas.jsonl` |
| `preparar.py` | Tira repetidas e curtas, limpa o texto e acrescenta os campos de PLN |
| `analisar.py` | Gera os números, os gráficos e a conferência de qualidade em `relatorios/` |

Tem também o `pipeline_pln.ipynb`, um notebook que mostra o mesmo processo passo a passo, com
explicação de cada etapa. Ele roda sozinho, sem precisar dos outros arquivos.

## O que foi coletado

A coleta padrão pega 3 páginas de cada uma das 11 categorias do site. Para a base do trabalho
usamos 12 páginas por categoria.

| | |
|---|---|
| Notícias coletadas | 1.147 |
| Repetidas descartadas | 129 |
| Curtas demais descartadas | 49 |
| **Notícias na base final** | **969** |
| Categorias | 11 (mais a subcategoria Oktoberfest) |
| Período | setembro de 2025 a setembro de 2026 |
| Palavras por notícia | de 21 a 1.616 (mediana 201) |
| Vocabulário | 16.418 palavras diferentes |

As categorias mais presentes são Ocorrências (148), Tempo (121), Notícias (119) e Destaques
(106). As menores são Falecidos e Diversos, com 48 cada.

## Decisões de coleta

**Coletamos por categoria, não pela página principal.** A listagem geral (`/noticias/`) só tem
2 páginas; as categorias vão muito mais fundo e ainda garantem variedade de assunto.

**O site bloqueia quem não parece navegador.** Toda requisição vai com um cabeçalho
`User-Agent` de navegador, senão a resposta é erro 403.

**A data e a categoria vêm do JSON-LD.** O texto visível mostra a data em formatos diferentes,
mas o WordPress publica um bloco `application/ld+json` com a informação certa.

**Tem espera entre as requisições.** O padrão é 1,5 segundo. As páginas antigas do site são
lentas, e numa tentativa com quatro coletas ao mesmo tempo o site começou a dar erro.

**A coleta é incremental.** O programa lê o que já foi salvo e não baixa de novo. Dá para
rodar hoje, rodar de novo semana que vem e só as notícias novas são baixadas. É assim que a
base se mantém atualizada.

## Decisões de limpeza

**Notícia repetida é achada pelo conteúdo, não pelo endereço.** O site republica a mesma nota
em dias seguidos, mudando o endereço para `-2`, `-3`, `-4`. Comparamos um código gerado a
partir do título e do texto, sem acento nem pontuação, então versões levemente diferentes da
mesma notícia geram o mesmo código.

**Textos com menos de 20 palavras saem da base.** São posts que só têm imagem ou vídeo: o
parágrafo existe, mas está vazio.

**Créditos e propaganda são removidos do texto.** `Fonte:`, `Foto:`, o convite para mandar
WhatsApp e a hashtag do blog aparecem nos mesmos parágrafos da notícia. Antes de escrever a
regra, olhamos a base: das 455 linhas que começavam com `Fonte:`, 454 estavam nas duas últimas
linhas do texto, o que confirma que é assinatura e não conteúdo. **624 notícias tinham algum
desses trechos.** Sem essa limpeza, `fonte` seria a 5ª palavra mais comum da base.

**O texto original nunca é apagado.** Cada etapa cria um campo novo. Isso importa porque
tarefas diferentes precisam de versões diferentes: procurar nomes de pessoas exige o texto com
maiúsculas e pontuação, enquanto classificar funciona melhor com o texto reduzido.

## Os campos de cada notícia

Do site vêm `titulo`, `data`, `categoria`, `texto`, `url` e `coletado_em`. O `preparar.py`
acrescenta:

| Campo | O que é |
|---|---|
| `texto_limpo` | o texto sem os créditos e a propaganda |
| `texto_normalizado` | título e texto juntos, em minúsculas, com acentos preservados |
| `palavras` | quantas palavras tem o texto limpo |
| `chave` | código do conteúdo, usado para achar repetidas |
| `tokens` | o texto separado em palavras e números, sem pontuação |
| `tokens_sem_vazias` | os tokens sem as 229 stopwords |
| `texto_para_modelo` | os tokens filtrados numa string só, pronto para TF-IDF |
| `radicais` | as palavras cortadas no radical (`notícias` → `notíc`) |
| `lemas` | as palavras do dicionário (`chuvas` → `chuva`, `foram` → `ser`) |
| `texto_radicais` e `texto_lemas` | as duas listas acima em forma de texto |

## Escolhas de pré-processamento

**Acentos são mantidos.** Tirar acento juntaria palavras diferentes. Só o código usado para
achar repetidas remove acento, e ali isso é proposital.

**A lista de stopwords está escrita no código**, em vez de vir de `nltk.download()`, para o
programa rodar sem internet e dar sempre o mesmo resultado. São as 229 palavras da lista do
NLTK mais algumas contrações comuns em notícia (`nesta`, `neste`, `desta`).

**O `não` é stopword**, seguindo o NLTK. Isso faz "não houve feridos" e "houve feridos" ficarem
iguais em `texto_para_modelo`. Quem for analisar negação ou sentimento deve usar `tokens`, que
guarda tudo.

**Stemming com Snowball, não RSLP.** O RSLP foi feito para o português e seria melhor, mas
precisa de `nltk.download('rslp')`. O Snowball já vem no pacote e funciona offline.

**Lematização com simplemma, não spaCy.** O spaCy precisa baixar um modelo de uns 15 MB. Em
troca, o simplemma erra em palavras ambíguas: ele devolve `melhorar` para `melhores`, quando o
certo seria `melhor`, porque não olha se a palavra é verbo ou adjetivo.

## Conferência de qualidade

O `analisar.py` termina checando a base: campo vazio, data que não dá para entender, endereço
repetido e conteúdo repetido. Na base atual, os quatro dão zero.

Ele também escolhe 20 notícias espalhadas pelo período e grava em
`relatorios/amostra_para_conferir.csv`, para abrir no site e comparar na mão. Fizemos essa
conferência e as 20 estavam certas: título, data, categoria e parágrafos batendo com a página.
O resultado está em `relatorios/amostra_conferida.csv`.

## Limitações

1. **Um site só.** Não dá para comparar como veículos diferentes contam o mesmo fato.
2. **A base é um recorte recente**, não o site inteiro, que tem cerca de 49 mil posts.
3. **Uma categoria por notícia**, mesmo quando o site usa mais de uma.
4. **Só achamos repetição idêntica.** Dois boletins de trânsito de dias diferentes passam
   como notícias distintas, mesmo tendo a mesma estrutura.
5. **Falecidos e Aniversários são listas de nomes** de pessoas comuns. Ficaram na base para
   representar o site, mas devem sair de tarefas que envolvam nome de pessoa.
6. **Nomes com número se quebram** na separação em palavras: `BR-470` vira `br` e `470`.

## Próximos passos

Busca por assunto e recomendação de notícia parecida, usando `texto_para_modelo` com TF-IDF.
Depois, classificação automática de categoria, que dá para avaliar comparando com a categoria
declarada pelo site.

## Onde ficam os arquivos

```
dados/noticias_coletadas.jsonl    tudo que foi baixado do site
dados/noticias_preparadas.jsonl   a base limpa, com os campos de PLN
dados/noticias_preparadas.csv     a mesma base em tabela, para abrir no Excel
relatorios/                       resumo.json, categorias.csv, gráficos e amostras
```

As duas pastas não vão para o repositório, porque são grandes e dá para gerar de novo com os
três programas.
