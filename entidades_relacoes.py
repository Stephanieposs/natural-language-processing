"""Reconhecimento de entidades nomeadas e extracao de relacoes."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from representacao_textual import calcular_hash_base, carregar_base_nlp


PROJECT_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_DIR / "data/processed"
REPORTS_DIR = PROJECT_DIR / "reports"
ENTITIES_JSONL_PATH = PROCESSED_DIR / "noticias_entidades.jsonl"
RELATIONS_CSV_PATH = PROCESSED_DIR / "noticias_relacoes.csv"
ENTITY_SUMMARY_PATH = REPORTS_DIR / "entities_summary.csv"
RELATION_SUMMARY_PATH = REPORTS_DIR / "relations_summary.csv"
SUMMARY_PATH = REPORTS_DIR / "summary.json"
SPACY_MODEL = "pt_core_news_sm"

SUBJECT_DEPS = {"nsubj", "nsubj:pass"}
COMPLEMENT_DEPS = {"obj", "iobj", "obl"}
LEADING_ARGUMENT_DEPS = {"case", "det"}
ARGUMENTOS_DESCARTAVEIS = {"que", "qual", "quais", "quem", "onde", "quando", "como"}


def carregar_nlp():
    try:
        import spacy
    except ImportError as error:
        raise RuntimeError(
            "Instale o spaCy para extrair entidades e relacoes: "
            "pip install -r requirements.txt"
        ) from error

    try:
        return spacy.load(SPACY_MODEL)
    except OSError as error:
        raise RuntimeError(
            f"Modelo {SPACY_MODEL} nao encontrado. Execute: "
            f"python -m spacy download {SPACY_MODEL}"
        ) from error


def montar_texto_noticia(registro):
    titulo = str(registro.get("title") or "").strip()
    conteudo = str(registro.get("content") or "").strip()
    if titulo and conteudo:
        return f"{titulo}\n{conteudo}"
    return titulo or conteudo


def campos_documento(document_id, registro):
    return {
        "document_id": int(document_id),
        "title": registro.get("title", ""),
        "published_at": registro.get("published_at", ""),
        "category": registro.get("category", ""),
        "url": registro.get("url", ""),
        "content_hash": registro.get("content_hash", ""),
    }


def obter_sintagma(token):
    tokens = list(token.subtree)
    inicio = min(t.i for t in tokens)
    fim = max(t.i for t in tokens) + 1
    return token.doc[inicio:fim].text


def entidade_do_token(token):
    return next(
        (ent for ent in token.doc.ents if ent.start <= token.i < ent.end),
        None,
    )


def limpar_sintagma_argumento(token):
    tokens = sorted(
        (t for t in token.subtree if not t.is_punct and not t.is_space),
        key=lambda t: t.i,
    )
    while tokens and tokens[0].dep_ in LEADING_ARGUMENT_DEPS:
        tokens.pop(0)
    return " ".join(t.text for t in tokens).strip()


def obter_argumento(token):
    entidade = entidade_do_token(token)
    if entidade is not None:
        return entidade.text
    return limpar_sintagma_argumento(token) or obter_sintagma(token)


def obter_rotulo_argumento(token):
    entidade = entidade_do_token(token)
    return entidade.label_ if entidade is not None else ""


def normalizar_preposicao(token):
    texto = token.text.lower()
    mapa = {
        "no": "em",
        "na": "em",
        "nos": "em",
        "nas": "em",
        "do": "de",
        "da": "de",
        "dos": "de",
        "das": "de",
        "ao": "a",
        "aos": "a",
        "\u00e0": "a",
        "\u00e0s": "a",
        "pelo": "por",
        "pela": "por",
        "pelos": "por",
        "pelas": "por",
    }
    return mapa.get(texto, token.lemma_.lower())


def sujeitos_do_verbo(verbo):
    sujeitos = [token for token in verbo.children if token.dep_ in SUBJECT_DEPS]
    if sujeitos or verbo.dep_ != "conj" or verbo.head.pos_ not in {"VERB", "AUX"}:
        return sujeitos
    return [token for token in verbo.head.children if token.dep_ in SUBJECT_DEPS]


def relacao_do_complemento(verbo, complemento):
    relacao = verbo.lemma_.lower()
    if complemento.dep_ == "obl":
        preposicao = next(
            (token for token in complemento.children if token.dep_ == "case"),
            None,
        )
        if preposicao is not None:
            relacao += "_" + normalizar_preposicao(preposicao)
    return relacao


def argumento_valido(texto):
    return bool(texto) and texto.casefold() not in ARGUMENTOS_DESCARTAVEIS


def mapa_sentencas(doc):
    return {sentenca.start: indice for indice, sentenca in enumerate(doc.sents, start=1)}


def extrair_entidades_doc(doc, metadados):
    entidades = []
    sentencas = mapa_sentencas(doc)
    for ent in doc.ents:
        sentenca = ent.sent
        entidades.append(
            {
                **metadados,
                "sentenca": int(sentencas.get(sentenca.start, 0)),
                "texto_sentenca": sentenca.text.strip(),
                "entidade": ent.text,
                "rotulo_entidade": ent.label_,
                "inicio": int(ent.start_char),
                "fim": int(ent.end_char),
            }
        )
    return entidades


def extrair_relacoes_doc(doc, metadados):
    relacoes = []
    for numero_sentenca, sentenca in enumerate(doc.sents, start=1):
        for verbo in sentenca:
            if verbo.pos_ not in {"VERB", "AUX"}:
                continue

            sujeitos = sujeitos_do_verbo(verbo)
            complementos = [
                token for token in verbo.children if token.dep_ in COMPLEMENT_DEPS
            ]
            for sujeito in sujeitos:
                for complemento in complementos:
                    sujeito_texto = obter_argumento(sujeito)
                    objeto_texto = obter_argumento(complemento)
                    if not argumento_valido(sujeito_texto) or not argumento_valido(
                        objeto_texto
                    ):
                        continue
                    relacoes.append(
                        {
                            **metadados,
                            "sentenca": numero_sentenca,
                            "texto_sentenca": sentenca.text.strip(),
                            "sujeito": sujeito_texto,
                            "rotulo_sujeito": obter_rotulo_argumento(sujeito),
                            "relacao": relacao_do_complemento(verbo, complemento),
                            "objeto": objeto_texto,
                            "rotulo_objeto": obter_rotulo_argumento(complemento),
                            "verbo": verbo.text,
                            "dependencia_objeto": complemento.dep_,
                        }
                    )
    return relacoes


def resumir_entidades(entidades_df):
    if entidades_df.empty:
        return pd.DataFrame(
            columns=[
                "rotulo_entidade",
                "quantidade_mencoes",
                "entidades_distintas",
                "principais_entidades",
            ]
        )

    linhas = []
    for rotulo, grupo in entidades_df.groupby("rotulo_entidade", sort=True):
        contagens = Counter(grupo["entidade"])
        linhas.append(
            {
                "rotulo_entidade": rotulo,
                "quantidade_mencoes": int(len(grupo)),
                "entidades_distintas": int(grupo["entidade"].nunique()),
                "principais_entidades": "; ".join(
                    f"{entidade}: {quantidade}"
                    for entidade, quantidade in contagens.most_common(15)
                ),
            }
        )
    return pd.DataFrame(linhas).sort_values(
        "quantidade_mencoes",
        ascending=False,
    )


def resumir_relacoes(relacoes_df):
    if relacoes_df.empty:
        return pd.DataFrame(
            columns=[
                "relacao",
                "quantidade",
                "pares_distintos",
                "principais_pares",
            ]
        )

    linhas = []
    for relacao, grupo in relacoes_df.groupby("relacao", sort=True):
        pares = Counter(zip(grupo["sujeito"], grupo["objeto"]))
        linhas.append(
            {
                "relacao": relacao,
                "quantidade": int(len(grupo)),
                "pares_distintos": int(
                    grupo[["sujeito", "objeto"]].drop_duplicates().shape[0]
                ),
                "principais_pares": "; ".join(
                    f"{sujeito} -> {objeto}: {quantidade}"
                    for (sujeito, objeto), quantidade in pares.most_common(10)
                ),
            }
        )
    return pd.DataFrame(linhas).sort_values("quantidade", ascending=False)


def salvar_jsonl(dataframe, caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_json(
        caminho,
        orient="records",
        lines=True,
        force_ascii=False,
        date_format="iso",
    )


def atualizar_resumo_geral(resumo_extracao):
    resumo = {}
    if SUMMARY_PATH.exists():
        resumo = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    resumo["information_extraction"] = resumo_extracao
    SUMMARY_PATH.write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extrair_entidades_e_relacoes(dataframe=None, verbose=True):
    dataframe = carregar_base_nlp() if dataframe is None else dataframe.copy()
    dataframe = dataframe.reset_index(drop=True)
    nlp = carregar_nlp()

    entidades = []
    relacoes = []
    total = len(dataframe)
    registros = list(dataframe.iterrows())
    textos = [montar_texto_noticia(registro) for _, registro in registros]
    metadados_documentos = [
        campos_documento(document_id, registro) for document_id, registro in registros
    ]

    for indice, (texto, metadados, doc) in enumerate(
        zip(textos, metadados_documentos, nlp.pipe(textos, batch_size=16)),
        start=1,
    ):
        if verbose and (indice == 1 or indice % 50 == 0):
            print(f"Processando noticia {indice}/{total}...", flush=True)
        if not texto:
            continue

        entidades.extend(extrair_entidades_doc(doc, metadados))
        relacoes.extend(extrair_relacoes_doc(doc, metadados))

    entidades_df = pd.DataFrame(entidades)
    relacoes_df = pd.DataFrame(relacoes)
    resumo_entidades = resumir_entidades(entidades_df)
    resumo_relacoes = resumir_relacoes(relacoes_df)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    salvar_jsonl(entidades_df, ENTITIES_JSONL_PATH)
    relacoes_df.to_csv(RELATIONS_CSV_PATH, index=False, encoding="utf-8")
    resumo_entidades.to_csv(ENTITY_SUMMARY_PATH, index=False, encoding="utf-8")
    resumo_relacoes.to_csv(RELATION_SUMMARY_PATH, index=False, encoding="utf-8")

    resumo = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "documents": int(total),
        "dataset_hash": calcular_hash_base(dataframe),
        "spacy_model": SPACY_MODEL,
        "entity_mentions": int(len(entidades_df)),
        "unique_entities": int(
            entidades_df["entidade"].nunique() if not entidades_df.empty else 0
        ),
        "relations": int(len(relacoes_df)),
        "files": {
            "entities": ENTITIES_JSONL_PATH.name,
            "relations": RELATIONS_CSV_PATH.name,
            "entity_summary": ENTITY_SUMMARY_PATH.name,
            "relation_summary": RELATION_SUMMARY_PATH.name,
        },
    }
    atualizar_resumo_geral(resumo)
    return entidades_df, relacoes_df, resumo


def main():
    entidades_df, relacoes_df, resumo = extrair_entidades_e_relacoes()
    print(
        f"Extracao concluida: {resumo['entity_mentions']} mencoes de entidades "
        f"e {resumo['relations']} relacoes em {resumo['documents']} noticias."
    )
    print(f"Entidades: {ENTITIES_JSONL_PATH}")
    print(f"Relacoes: {RELATIONS_CSV_PATH}")
    print(f"Resumo de entidades: {ENTITY_SUMMARY_PATH}")
    print(f"Resumo de relacoes: {RELATION_SUMMARY_PATH}")
    if not entidades_df.empty:
        print("\nEntidades por rotulo:")
        print(resumir_entidades(entidades_df).to_string(index=False))
    if not relacoes_df.empty:
        print("\nRelacoes mais frequentes:")
        print(resumir_relacoes(relacoes_df).head(15).to_string(index=False))


if __name__ == "__main__":
    main()
