from __future__ import annotations

import logging
import re
from functools import lru_cache

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import DocChunk, DocSource
from .embedding import embed_text, embed_texts, tokenize
from .glossary import expand_query


logger = logging.getLogger(__name__)
COLLECTION_NAME = "manual_chunks_demo_v2"
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "are",
    "was",
    "were",
    "has",
    "have",
    "into",
}
ERROR_CODE_RE = re.compile(r"\b[a-z]{1,3}-\d{1,3}\b", flags=re.IGNORECASE)


def _stem(token: str) -> str:
    token = token.lower().strip("._-")
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _term_set(text: str) -> set[str]:
    return {
        _stem(token)
        for token in tokenize(text)
        if token.isascii() and len(token) > 1 and token.lower() not in STOPWORDS
    }


def _lexical_overlap(query_terms: set[str], chunk: DocChunk) -> float:
    if not query_terms:
        return 0.0
    section_terms = _term_set(f"{chunk.section} {chunk.keywords}")
    body_terms = _term_set(chunk.text)
    weighted_hits = sum(
        1.0 if term in section_terms else 0.6 if term in body_terms else 0.0
        for term in query_terms
    )
    return weighted_hits / len(query_terms)


def _error_code_boost(query: str, chunk: DocChunk) -> float:
    codes = {match.upper() for match in ERROR_CODE_RE.findall(query)}
    if not codes:
        return 0.0
    labelled = f"{chunk.section} {chunk.keywords}".upper()
    return 0.3 * sum(1 for code in codes if code in labelled) / len(codes)


@lru_cache(maxsize=1)
def _client():
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(settings.chroma_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _collection():
    return _client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def rebuild_index(db: Session) -> int:
    chunks = db.scalars(select(DocChunk).order_by(DocChunk.id)).all()
    try:
        _client().delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = _collection()
    if not chunks:
        return 0
    collection.add(
        ids=[chunk.id for chunk in chunks],
        embeddings=embed_texts([chunk.text for chunk in chunks]),
        documents=[chunk.text for chunk in chunks],
        metadatas=[
            {
                "doc_id": chunk.doc_id,
                "page_no": chunk.page_no,
                "section": chunk.section,
                "model": chunk.model,
                "title": chunk.doc.title if chunk.doc else "Service manual",
                "is_demo": True,
            }
            for chunk in chunks
        ],
    )
    return len(chunks)


def _evidence_from_chunks(
    db: Session,
    chunk_rows: list[DocChunk],
    scores: dict[str, float],
    mode: str,
) -> list[dict]:
    evidence: list[dict] = []
    for chunk in chunk_rows:
        doc_title = chunk.doc.title if chunk.doc else "Service manual"
        evidence.append(
            {
                "chunk_id": chunk.id,
                "doc_id": chunk.doc_id,
                "title": doc_title,
                "page": chunk.page_no,
                "section": chunk.section,
                "model": chunk.model,
                "text": chunk.text,
                "score": round(scores.get(chunk.id, 0.0), 4),
                "mode": mode,
            }
        )
    return evidence


def _fallback_search(db: Session, query: str, model: str, top_k: int) -> list[dict]:
    expanded = expand_query(query)
    tokens = [token for token in expanded.lower().replace("/", " ").split() if len(token) > 2]
    candidates = db.scalars(
        select(DocChunk)
        .where(or_(DocChunk.model == model, DocChunk.model == "ALL"))
        .limit(80)
    ).all()
    scored: list[tuple[float, DocChunk]] = []
    for chunk in candidates:
        haystack = f"{chunk.text} {chunk.keywords} {chunk.section}".lower()
        hits = sum(1 for token in tokens if token in haystack)
        if hits:
            scored.append((float(hits), chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    rows = [chunk for _, chunk in scored[:top_k]]
    max_hits = scored[0][0] if scored else 1.0
    scores = {chunk.id: score / max_hits for score, chunk in scored[:top_k]}
    return _evidence_from_chunks(db, rows, scores, "mysql_fallback")


def search_manual(db: Session, query: str, model: str, top_k: int = 4) -> list[dict]:
    if not query.strip():
        return []
    try:
        collection = _collection()
        count = collection.count()
        if count == 0:
            return _fallback_search(db, query, model, top_k)
        n_results = min(count, max(top_k * 4, 12))
        result = collection.query(
            query_embeddings=[embed_text(query)],
            n_results=n_results,
            where={"$or": [{"model": model}, {"model": "ALL"}]},
            include=["metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        if not ids:
            return _fallback_search(db, query, model, top_k)
        score_map = {
            chunk_id: max(0.0, 1.0 - float(distance))
            for chunk_id, distance in zip(ids, distances)
        }
        rows = db.scalars(select(DocChunk).where(DocChunk.id.in_(ids))).all()
        by_id = {row.id: row for row in rows}
        ordered = [by_id[chunk_id] for chunk_id in ids if chunk_id in by_id]
        query_terms = _term_set(query)
        reranked: list[tuple[float, DocChunk]] = []
        for chunk in ordered:
            overlap = _lexical_overlap(query_terms, chunk)
            combined = (
                0.4 * score_map.get(chunk.id, 0.0)
                + 0.6 * overlap
                + _error_code_boost(query, chunk)
            )
            score_map[chunk.id] = combined
            reranked.append((combined, chunk))
        reranked.sort(key=lambda item: item[0], reverse=True)
        return _evidence_from_chunks(db, [chunk for _, chunk in reranked[:top_k]], score_map, "chroma")
    except Exception as exc:
        logger.warning("Chroma retrieval failed, falling back to MySQL: %s", exc)
        return _fallback_search(db, query, model, top_k)

