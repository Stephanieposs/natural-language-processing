# Plano de tarefas — Coleta, organização e pré-processamento (PLN)

Branch de trabalho: `feature/coleta-preprocessamento-pln` (nada commitado ainda).
**Estado em 2026-09-06 (fim do dia):** coleta, consolidação, análise exploratória, pré-processamento, revisão
manual e documentação concluídos. Pendente apenas a decisão sobre versionar `data/` e `reports/` e o commit.
Legenda: `[x]` concluído · `[~]` em andamento · `[ ]` pendente.

Objetivo: transformar o scraper funcional em uma entrega justificada de
**coleta reproduzível + base organizada + análise exploratória + pré-processamento**
de notícias locais de Blumenau (Blog do Jaime), com limitações reconhecidas.

---

## Etapa 0 — Preparação e reconhecimento da fonte

- [x] Criar branch `feature/coleta-preprocessamento-pln`.
- [x] Ler `scraper.py`, `analyze.py`, `preprocess.py`, testes e README existentes.
- [x] Verificar `robots.txt` do portal → responde 200 com corpo vazio (nenhuma restrição declarada).
- [x] Verificar que o portal bloqueia (403) User-Agent genérico, mas aceita o UA completo do scraper.
- [x] Mapear categorias existentes no portal (11): `ocorrencias`, `eventos`, `destaques`, `tempo`,
      `falecidos`, `aniversarios`, `noticias`, `diversos`, `saude`, `esportes`, `transito`.
- [x] Medir paginação: `/noticias/` tem só 2 páginas reais (16 links cada; da página 3 em diante
      repete os 16 mais recentes). Páginas de categoria são arquivos WordPress reais: 10 links por
      página, paginação profunda (página 40 de Ocorrências ainda responde).
- [x] Estimar acervo total: API REST (`/wp-json/wp/v2/posts`) informa 49.140 posts; sitemap com 30 arquivos.
      → A base coletada será uma **amostra**; isto deve ser documentado como limitação.
- [x] Adicionar parâmetro `--raw` ao `scraper.py` para que coletas paralelas gravem arquivos brutos separados.
- [x] Criar `merge_raw.py` para consolidar arquivos parciais em `data/raw/noticias.jsonl` e regenerar a base processada.
- [x] Escrever testes para `merge_raw.py`; rodar `pytest -q` (19 testes verdes).
- [x] Criar `collect.sh` (plano de coleta por categoria, reproduzível, com logs por lote).

## Etapa 1 — Coleta ampliada (`--delay 1.5 --minimum-words 20`)

> **Incidente registrado:** a primeira tentativa usou 4 subagentes, um por grupo de categorias. Três foram encerrados pelo watchdog (10 min sem atividade enquanto esperavam o scraper) e seus processos morreram sem gravar nada. Além disso, 4 coletas simultâneas sobrecarregaram o portal (páginas de arquivo custam ~5 s ao servidor; artigos vêm do cache em 0,2 s), gerando timeouts. **Nova estratégia:** 2 lotes via `collect.sh`, rodando em background na sessão principal.

Cada categoria grava em `data/raw/parts/<categoria>.jsonl` e `data/processed/parts/<categoria>.jsonl`
(um arquivo por categoria preserva a proveniência: em qual listagem a notícia foi encontrada).
Logs em `data/raw/parts/logs/<categoria>.log`.

- [x] **Lote 1** (`./collect.sh lote1 ocorrencias:15 eventos:15 tempo:12 transito:10`) — 13:03 → 14:42, 2 avisos (timeouts recuperados).
- [x] **Lote 2** (`./collect.sh lote2 noticias:12 destaques:12 diversos:8 geral:2 esportes:10 falecidos:5 aniversarios:5`) — 13:03 → 14:42, 1 aviso.
- [x] **Saúde** (`category/saude`, 10 pág.): iniciada pelo Agente D antes do incidente; processo seguiu vivo e concluiu (3 avisos).
- [x] Registrar por listagem: páginas lidas, coletadas, únicas, republicações, curtas → tabela no README
      (116 páginas, 1.163 registros, 0 erros de coleta; só timeouts recuperados pelo retry).

## Etapa 2 — Consolidação da base

- [x] `python merge_raw.py data/raw/parts/*.jsonl --minimum-words 20` → `data/raw/noticias.jsonl`,
      `data/processed/noticias.jsonl`, `data/processed/noticias.csv`, `reports/listing_vs_category.csv`.
- [x] Conferir contagens: **1.140** URLs distintas no bruto → **977** únicas; 128 republicações e 35 curtas removidas
      (23 URLs apareceram em mais de uma listagem e foram unidas).
- [x] Implementar relatório de proveniência em `merge_raw.py` (`reports/listing_vs_category.csv`:
      listagem de origem × categoria declarada no JSON-LD), com teste.

## Etapa 3 — Análise exploratória e qualidade

- [x] `python analyze.py --minimum-words 20 --sample-size 20 --top-terms 30` → `reports/` (8 arquivos + 2 SVG).
- [x] Ler `reports/summary.json`, `category_distribution.csv`, `news_by_month.csv`, `quality_issues.csv`
      → 0 datas inválidas, 0 campos ausentes na base processada, 35 problemas de qualidade (todos textos curtos/sem texto).
- [x] Revisão manual de `reports/review_sample.csv`: agente conferiu 20 notícias na URL original (título, data,
      categoria, parágrafos, vazamento de rodapé). 15 ok automáticas + 5 falsos positivos de conteúdo reconferidos
      manualmente com o parser do projeto → **20/20 corretas**. Resultado preservado em
      `reports/review_sample.revisado.csv` (o `analyze.py` regrava `review_sample.csv` em branco).
- [x] Implementar em `analyze.py` os termos mais frequentes (geral e por categoria → `reports/top_terms.csv`)
      e o tamanho do vocabulário (`processed.vocabulary_size` em `summary.json`), com testes.
- [x] Rodar e interpretar `reports/top_terms.csv` → assinaturas lexicais por categoria descritas no README.

## Etapa 4 — Pré-processamento para PLN

- [x] Ampliar a lista de stopwords de ~90 para 229 termos (base NLTK português + contrações jornalísticas),
      mantida inline (sem downloads); teste atualizado e novo teste de cobertura da lista.
- [x] `python preprocess.py` → `data/processed/noticias_nlp.jsonl` (977 registros, 8,7 MB; campos `text_normalized`,
      `tokens`, `tokens_without_stopwords`, `text_for_model`).
- [x] Conferir amostra do arquivo gerado: 264 tokens/notícia em média → 169 sem stopwords (−36%); vocabulário 15.362.

## Etapa 5 — Documentação

- [x] Atualizar `README.md` com resultados reais: total coletado, distribuição por categoria, período coberto,
      duplicadas, curtas, arquivos gerados, limitações (amostra vs. 49k posts, paginação de `/noticias/`,
      categorias multi-rótulo, textos formulaicos como falecidos/aniversários) e próximos usos
      (classificação, NER, busca/BM25, sumarização, chatbot).
- [x] Atualizar este `TASKS.md` com o estado final.

## Etapa 6 — Fechamento

- [x] `pytest -q` verde (22 testes).
- [x] `git status` revisado; **não commitado** (decisão do usuário). Alterados: `README.md`, `analyze.py`, `preprocess.py`,
      `scraper.py`, `tests/test_analyze.py`, `tests/test_preprocess.py`. Novos: `TASKS.md`, `collect.sh`, `merge_raw.py`,
      `tests/test_merge_raw.py`. Ignorados pelo git: `data/`, `reports/`.
- [ ] **Decisão pendente do usuário:** `data/` e `reports/` estão no `.gitignore`. Se dados e relatórios fizerem parte
      da entrega, remover as regras do `.gitignore` (ou anexar os arquivos separadamente) antes do commit.

---

## Registro de decisões e descobertas

| Data | Decisão / descoberta | Motivo |
|------|----------------------|--------|
| 2026-09-06 | Coletar por categorias em vez de apenas `/noticias/` | A listagem geral só pagina 2 páginas; categorias paginam fundo e garantem diversidade. |
| 2026-09-06 | Adicionar `--raw` ao scraper + `merge_raw.py` | Coletas paralelas gravavam no mesmo `data/raw/noticias.jsonl` (leitura → merge → escrita), gerando condição de corrida. |
| 2026-09-06 | Delay de 1,5 s por processo, no máximo 2 lotes simultâneos | Tentativa com 4 processos causou timeouts no portal (arquivos de categoria são caros para o servidor). `robots.txt` vazio, mas carga moderada é uma obrigação ética. |
| 2026-09-06 | Coleta executada pela sessão principal, não por subagentes | Subagentes que apenas esperam um processo longo são mortos por inatividade após 10 min, levando o processo junto. Subagentes ficam reservados para tarefas ativas (revisão manual da amostra). |
| 2026-09-06 | Incluir `falecidos` e `aniversarios` com poucas páginas | São categorias reais do portal (diversidade), mas textos formulaicos; poucas páginas evitam enviesar a base. |
| 2026-09-06 | Smoke test em `category/saude` (1 pág.): 10 coletadas, 4 únicas, 6 duplicadas | O portal **republica a mesma nota em dias consecutivos** com URLs `-2`, `-3`, `-4`. A deduplicação por hash (título+conteúdo normalizados) está funcionando como previsto; o rendimento de únicas por página é menor que 10, o que justifica coletar mais páginas. |
| 2026-09-06 | Stopwords ampliadas para a lista NLTK-pt + contrações (`nesta`, `deste`...) | A lista original (~90) deixava passar `será`, `são`, `está`, `foram`, poluindo `text_for_model` e os termos frequentes. `não` fica como stopword (padrão NLTK); o campo `tokens` preserva tudo para tarefas sensíveis à negação. |
| 2026-09-06 | Registros com 0 palavras são posts só com imagem/vídeo, não falha do parser | Inspeção do HTML de 2 casos: o container `.elementor-widget-theme-post-content` existe, mas contém apenas `<img>` ou `<iframe>` e nenhum `<p>`. Concentram-se em Diversos (mensagens do padre em vídeo) e Saúde (cartazes de horários). O filtro `--minimum-words 20` os remove da base processada; eles ficam na bruta. |
| 2026-09-06 | Categoria declarada pode vir composta (`Notícias, Uncategorized`) ou como sub-categoria (`Oktoberfest` dentro de Eventos) | Vem do `articleSection` do JSON-LD do portal. Mantido como está na base bruta; documentado como característica multi-rótulo. |
| 2026-09-06 | 5 "divergências de conteúdo" da revisão automática reclassificadas como `ok` | Re-parse das 5 páginas ao vivo com `parse_article` produziu conteúdo idêntico ao armazenado; a leitura confirma o corpo da notícia. Causa: a 1ª versão do script do agente extraía texto sem separador de espaço (palavras coladas em `<br>`/negrito), quebrando a busca por substring; corrigido, encontrou 100% dos parágrafos das 20 notícias. |
| 2026-09-06 | Não usar a API REST agora | O enunciado pede web scraping; a API fica registrada como alternativa mais eficiente para coletas futuras. |
