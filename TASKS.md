# O que foi feito

Lista do que já está pronto e das decisões que tomamos durante o trabalho.

## Coleta

- [x] Descobrir como o site organiza as notícias e como paginar as categorias
- [x] Resolver o bloqueio 403 mandando `User-Agent` de navegador
- [x] Ler data e categoria do JSON-LD, que é mais confiável que o texto da página
- [x] Aceitar o layout do Elementor, usado no tema atual do site
- [x] Filtrar os links: separar notícia de menu, categoria, paginação e imagem
- [x] Deixar a coleta incremental, para não baixar de novo o que já foi salvo
- [x] Coletar 11 categorias — 1.147 notícias baixadas

## Limpeza e preparação

- [x] Achar notícias repetidas comparando o conteúdo, não o endereço (129 encontradas)
- [x] Tirar textos com menos de 20 palavras (49 removidos)
- [x] Remover créditos (`Fonte:`, `Foto:`) e propaganda do blog — 624 notícias tinham
- [x] Normalizar o texto mantendo os acentos
- [x] Separar em palavras, deixando a pontuação de fora
- [x] Remover as 229 stopwords do português
- [x] Gerar radicais (stemming) com o Snowball
- [x] Gerar lemas (lematização) com o simplemma

## Análise

- [x] Contar notícias por categoria e por mês
- [x] Medir o tamanho dos textos e o vocabulário
- [x] Listar as palavras mais comuns de cada categoria
- [x] Conferir a qualidade: campo vazio, data estranha, repetição (tudo zero)
- [x] Escolher 20 notícias e conferir na mão contra o site — as 20 estavam certas
- [x] Fazer os gráficos

## Documentação

- [x] README com os números reais, as decisões e as limitações
- [x] Notebook explicando o processo passo a passo
- [x] CLAUDE.md com o contexto do projeto

## Ainda falta

- [ ] Busca por assunto e recomendação de notícia parecida
- [ ] Análise de sentimento (positivo ou negativo)
- [ ] Comparar com outro site de notícias da região

## Decisões e por quê

| Decisão | Motivo |
|---|---|
| Coletar por categoria em vez da página principal | A listagem geral só tem 2 páginas; as categorias vão bem mais fundo e ainda dão variedade de assunto |
| Espera de 1,5 segundo entre as requisições | Numa tentativa com 4 coletas ao mesmo tempo o site começou a dar erro. As páginas antigas dele são lentas |
| Achar repetição pelo conteúdo, não pelo endereço | O site republica a mesma nota em dias seguidos, mudando o endereço para `-2`, `-3`, `-4`. Pelo endereço não daria para perceber |
| Incluir Falecidos e Aniversários com poucas páginas | São categorias reais do site, mas o texto é sempre igual (lista de nomes). Poucas páginas evitam que elas dominem a base |
| Cortar créditos e propaganda do texto | Antes de escrever a regra, contamos: das 455 linhas começando com `Fonte:`, 454 estavam nas duas últimas linhas do texto. É assinatura, não notícia. Sem isso, `fonte` seria a 5ª palavra mais comum |
| Contar as palavras depois de limpar os créditos | Assim o filtro de 20 palavras mede o texto de verdade. Isso tirou 14 posts que eram só lista de datas comemorativas e aviso de missa, cujo texto era quase todo crédito e @perfil |
| Escrever as stopwords no código | Usar `nltk.download()` faria o programa depender de internet e o resultado poderia mudar conforme a versão baixada |
| Manter o `não` como stopword | É o padrão do NLTK. A negação se perde, e por isso guardamos também o campo `tokens`, sem filtro nenhum |
| Snowball em vez de RSLP | O RSLP é feito para o português e seria melhor, mas precisa baixar um arquivo extra |
| simplemma em vez de spaCy | O spaCy precisa baixar um modelo de 15 MB. O simplemma erra em palavras ambíguas (`melhores` → `melhorar`), o que é aceitável para busca |
| Não usar a API do WordPress | O trabalho pede web scraping. A API fica anotada como opção mais rápida para o futuro |
| Três programas em vez de um só | `coletar`, `preparar` e `analisar` são etapas separadas: dá para rodar a análise várias vezes sem coletar de novo |
| Textos com 0 palavras não são erro do código | Olhamos o HTML de alguns: o parágrafo existe, mas só tem imagem ou vídeo dentro. São posts de mensagem em vídeo e cartaz de horário |
