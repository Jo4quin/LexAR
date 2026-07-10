"""Vinculos entre normas a nivel documento (Fase 5) y helpers de carga para la app.

`build_norm_links()` consolida tres fuentes ya generadas por Fases 2-3:
- pares semanticos de `analysis_candidates.parquet` (similitud >= umbral p90),
- el grafo oficial de modificaciones de Infoleg (`relations.csv`),
- las etiquetas/explicaciones de `candidate_classifications.parquet`.
Los vinculos oficiales entran aunque no tengan par semantico: un abogado que abre una ley
quiere ver sus modificatorias registradas aunque el texto no se parezca.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import (
    CANDIDATES_PATH,
    CLASSIFICATIONS_PATH,
    NORM_LINKS_PATH,
    RELATIONS_PATH,
    SIMILARITY_THRESHOLD,
)


def _doc_pair_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["document_id_a"] = np.minimum(df["document_a_id"], df["document_b_id"])
    df["document_id_b"] = np.maximum(df["document_a_id"], df["document_b_id"])
    return df


def build_norm_links() -> pd.DataFrame:
    # 1. Pares semanticos agregados a nivel documento.
    candidates = pd.read_parquet(
        CANDIDATES_PATH,
        columns=["pair_key", "document_a_id", "document_b_id", "similarity_score"],
    )
    scoped = _doc_pair_columns(candidates[candidates["similarity_score"] >= SIMILARITY_THRESHOLD])
    semantic = (
        scoped.groupby(["document_id_a", "document_id_b"])
        .agg(
            n_fragment_pairs=("pair_key", "size"),
            max_similarity=("similarity_score", "max"),
            mean_similarity=("similarity_score", "mean"),
        )
        .reset_index()
    )

    # 2. Etiqueta dominante y explicaciones de la Fase 3 (excluyendo boilerplate del voto:
    # una formula de cierre compartida no dice nada de la relacion juridica entre las normas).
    classifications = _doc_pair_columns(pd.read_parquet(
        CLASSIFICATIONS_PATH,
        columns=["document_a_id", "document_b_id", "final_label", "final_explanation", "rule_applied"],
    ))
    voting = classifications[classifications["rule_applied"] != "rule:boilerplate"]
    dominant = (
        voting.groupby(["document_id_a", "document_id_b"])["final_label"]
        .agg(lambda labels: labels.mode().iloc[0])
        .rename("dominant_label")
        .reset_index()
    )
    llm_explained = voting[voting["rule_applied"].isna() & voting["final_explanation"].notna()]
    explanations = (
        llm_explained.groupby(["document_id_a", "document_id_b"])["final_explanation"]
        .agg(lambda expl: json.dumps(expl.head(3).tolist(), ensure_ascii=False))
        .rename("sample_explanations")
        .reset_index()
    )
    semantic = semantic.merge(dominant, on=["document_id_a", "document_id_b"], how="left")
    semantic = semantic.merge(explanations, on=["document_id_a", "document_id_b"], how="left")
    semantic["dominant_label"] = semantic["dominant_label"].fillna("neutral")

    # 3. Grafo oficial de Infoleg, con direccion (source modifica a target).
    relations = pd.read_csv(
        RELATIONS_PATH,
        usecols=["source_document_id", "target_document_id"],
        dtype=str,
        keep_default_na=False,
    ).drop_duplicates()
    relations = relations[(relations["source_document_id"] != "") & (relations["target_document_id"] != "")]
    official = relations.rename(
        columns={"source_document_id": "document_a_id", "target_document_id": "document_b_id"}
    )
    official = _doc_pair_columns(official)
    official["official_direction"] = np.where(
        official["document_a_id"] == official["document_id_a"], "a_modifies_b", "b_modifies_a"
    )
    directions = (
        official.groupby(["document_id_a", "document_id_b"])["official_direction"]
        .agg(lambda d: d.iloc[0] if d.nunique() == 1 else "mutual")
        .reset_index()
    )

    # 4. Union semantico + oficial.
    links = semantic.merge(directions, on=["document_id_a", "document_id_b"], how="outer", indicator=True)
    links["link_source"] = links["_merge"].map(
        {"left_only": "semantic", "right_only": "official", "both": "both"}
    )
    links = links.drop(columns="_merge")
    links.loc[links["link_source"] == "official", "dominant_label"] = "possible_modification"
    links["doc_pair_key"] = links["document_id_a"] + "|" + links["document_id_b"]
    links.to_parquet(NORM_LINKS_PATH, index=False)
    print(
        f"norm_links: {len(links):,} vinculos "
        f"({(links['link_source'] == 'semantic').sum():,} semanticos, "
        f"{(links['link_source'] == 'official').sum():,} oficiales, "
        f"{(links['link_source'] == 'both').sum():,} ambos)"
    )
    return links


def build_law_case_links(case_fragments: pd.DataFrame, case_embeddings: np.ndarray, top_k: int = 8) -> pd.DataFrame:
    """Vinculo ley↔fallo (Fase 4.4): busca cada fragmento de fallo contra el indice FAISS de
    leyes y agrega a nivel (document_id, case_id). Sin text_a/text_b en la tabla bulk — misma
    regla de memoria que analysis_candidates (ver CLAUDE.md)."""
    from .config import LAW_CASE_LINKS_PATH
    from .retrieval import load_law_index

    law = load_law_index()
    scores, neighbor_idx = law.index.search(
        np.ascontiguousarray(case_embeddings.astype(np.float32)), top_k
    )

    law_doc_ids = law.fragments["document_id"].to_numpy()
    law_fragment_ids = law.fragments["fragment_id"].to_numpy()
    pairs = pd.DataFrame({
        "case_id": case_fragments["case_id"].to_numpy().repeat(top_k),
        "case_fragment_id": case_fragments["fragment_id"].to_numpy().repeat(top_k),
        "document_id": law_doc_ids[neighbor_idx.ravel()],
        "law_fragment_id": law_fragment_ids[neighbor_idx.ravel()],
        "similarity_score": scores.ravel(),
    })
    pairs = pairs[pairs["similarity_score"] > 0]

    best = pairs.sort_values("similarity_score", ascending=False).drop_duplicates(["case_id", "document_id"])
    counts = pairs.groupby(["case_id", "document_id"]).agg(
        n_fragment_pairs=("similarity_score", "size"),
        mean_similarity=("similarity_score", "mean"),
    )
    links = best.merge(counts, on=["case_id", "document_id"]).rename(
        columns={"similarity_score": "max_similarity"}
    )
    links = links.sort_values("max_similarity", ascending=False).reset_index(drop=True)
    LAW_CASE_LINKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    links.to_parquet(LAW_CASE_LINKS_PATH, index=False)
    print(f"law_case_links: {len(links):,} pares (documento, fallo); "
          f"{links['case_id'].nunique():,} fallos, {links['document_id'].nunique():,} normas")
    return links


def load_norm_links() -> pd.DataFrame:
    assert NORM_LINKS_PATH.exists(), f"No existe {NORM_LINKS_PATH} — correr la Fase 5 primero."
    return pd.read_parquet(NORM_LINKS_PATH)


def links_for_document(norm_links: pd.DataFrame, document_id: str) -> pd.DataFrame:
    """Vinculos de una norma, con `other_document_id` ya resuelto y direccion legible."""
    mask = (norm_links["document_id_a"] == document_id) | (norm_links["document_id_b"] == document_id)
    links = norm_links[mask].copy()
    is_a = links["document_id_a"] == document_id
    links["other_document_id"] = np.where(is_a, links["document_id_b"], links["document_id_a"])
    direction = links["official_direction"].fillna("")
    # El caso sin direccion oficial (vinculo solo semantico) va primero: si no, la condicion
    # `(direction == "a_modifies_b") == is_a` matchea con direction == "" cuando is_a es False
    # y etiqueta vinculos semanticos como "esta norma modifica a la vinculada".
    links["direccion_oficial"] = np.select(
        [
            direction == "",
            direction == "mutual",
            (direction == "a_modifies_b") == is_a,
        ],
        ["", "se modifican mutuamente", "esta norma modifica a la vinculada"],
        default="la vinculada modifica a esta norma",
    )
    return links.sort_values(["link_source", "max_similarity"], ascending=[True, False])


def count_later_modifications(norm_links: pd.DataFrame, document_id: str) -> int:
    """Cantidad de normas que modifican a esta (advertencia de vigencia en el explorador)."""
    links = links_for_document(norm_links, document_id)
    return int((links["direccion_oficial"] == "la vinculada modifica a esta norma").sum())
