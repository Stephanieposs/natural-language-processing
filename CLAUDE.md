# CLAUDE.md

Contexto do projeto, para abrir em outra máquina ou continuar depois.

## O que é

Trabalho da Etapa Prática 1 de PLN (FURB). Coleta notícias de Blumenau do portal Blog do Jaime
por web scraping, limpa e prepara o texto para tarefas de PLN.

**Estado:** base com 969 notícias de 11 categorias, publicadas entre setembro de 2025 e
setembro de 2026. Coleta, limpeza, preparação e análise funcionando.

**Branch de trabalho:** `feature/coleta-preprocessamento-pln`. A `master` está desatualizada.

## Preparar o ambiente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Precisa de Python 3.10 ou mais novo.

## Os arquivos

| Arquivo | O que faz |
|---|---|
| `coletar.py` | Baixa as notícias do site e salva em `dados/noticias_coletadas.jsonl` |
| `preparar.py` | Limpa o texto, tira repetidas e curtas, gera os campos de PLN |
| `analisar.py` | Estatísticas, gráficos e conferência de qualidade em `relatorios/` |
| `pipeline_pln.ipynb` | O mesmo processo em notebook, explicado passo a passo |
| `README.md` | Documentação do trabalho, com os números e as decisões |
| `TASKS.md` | O que já foi feito e por quê |

**`coletar.py`** — percorre as categorias do site, acha os links de notícia nas listagens e
extrai título, data, categoria e texto de cada uma. Precisa mandar `User-Agent` de navegador,
senão o site responde 403. A data e a categoria vêm do JSON-LD, porque o texto visível usa
formatos diferentes. O site usa o tema Elementor, então o corpo pode estar em
`.elementor-widget-theme-post-content` e não na `.entry-content` de sempre. A coleta é
incremental: o que já está salvo não é baixado de novo.

**`preparar.py`** — limpa créditos e propaganda, normaliza, separa em palavras, tira stopwords,
gera radicais e lemas. Também descarta notícias repetidas (comparando um hash do conteúdo) e
curtas demais. Nunca altera o `texto` original; tudo que faz vira campo novo.

**`analisar.py`** — conta por categoria e por mês, mede o tamanho dos textos, lista as palavras
mais comuns de cada categoria, confere a qualidade da base (campo vazio, data estranha,
repetição) e escolhe uma amostra para conferir na mão. Gera gráficos com matplotlib.

## Comandos

```bash
python coletar.py                    # 3 páginas por categoria
python coletar.py --paginas 12       # a coleta usada no trabalho, demora bastante
python preparar.py
python analisar.py
```

## Coisas para não esquecer

- **Não diminuir a espera entre as requisições.** O padrão é 1,5 segundo. Uma tentativa com
  quatro coletas simultâneas fez o site começar a dar erro.
- **O `texto` original nunca muda.** Toda etapa cria campo novo (`texto_limpo`, `tokens`,
  `radicais`, `lemas`). Isso é proposital: cada tarefa precisa de uma versão diferente.
- **Nada de baixar dados em tempo de execução.** Por isso Snowball em vez de RSLP e simplemma
  em vez de spaCy: os dois exigiriam download e quebrariam a reprodutibilidade.
- **Tudo em português**: nomes de função, comentários, docstrings e mensagens.
- **O notebook repete o código dos scripts** para poder rodar sozinho. Mexeu numa função,
  atualize os dois lugares.
- **`dados/` e `relatorios/` não vão para o repositório.** Ao clonar em outra máquina, vêm
  vazios: é preciso rodar `python coletar.py --paginas 12`, que leva mais de uma hora.
- **Não tem teste automatizado.** A verificação é rodar os três programas e conferir os
  números do `analisar.py`, que checa campo vazio, data inválida e repetição.

## Como o trabalho é conduzido

- Sempre em branch, nunca direto na `master`.
- Não commitar sem o Cristian pedir.
- `TASKS.md` guarda o que foi feito e as decisões com a justificativa.
- O código deve parecer trabalho de faculdade: função curta com nome óbvio, comentário
  explicando o porquê, sem abstração a mais.

## O que falta

- **Busca e recomendação**: próximo passo, usando `texto_para_modelo` com TF-IDF.
- **Análise de sentimento**: pedido, ainda não começado. Medir se a notícia é positiva ou
  negativa dá; medir imparcialidade não, com um site só e sem dado anotado para comparar.
- **Comparar com outro site**: seria o único item da rubrica ainda em aberto.
