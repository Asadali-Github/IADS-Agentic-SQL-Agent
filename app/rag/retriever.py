"""Oracle-backed retriever for RAG documents."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from app.rag.documents import load_documents
from app.rag.embeddings import build_search_text, extract_search_terms
from app.rag.oci_embeddings import OCITextEmbeddingClient
from app.sql.oracle_connection import connect_adb

ConnectionFactory = Callable[[], Any]


class OracleRAGRetriever:
    """Store and retrieve RAG documents from Oracle Autonomous Database."""

    def __init__(
        self,
        documents: list[dict] | None = None,
        top_k: int = 4,
        min_relevance_ratio: float = 0.3,
        connection_factory: ConnectionFactory | None = None,
        embedding_client: OCITextEmbeddingClient | None = None,
        table_name: str = "APP_RAG_DOCUMENTS",
        auto_seed: bool | None = None,
    ) -> None:
        self.documents = documents or load_documents()
        self.top_k = top_k
        self.min_relevance_ratio = min_relevance_ratio
        self.connection_factory = connection_factory or connect_adb
        self.embedding_client = embedding_client
        self.table_name = table_name

        self.seed_error: str | None = None
        should_seed = auto_seed if auto_seed is not None else self._auto_seed_enabled()
        if should_seed:
            try:
                self.seed_documents()
            except Exception as exc:  # pragma: no cover - depends on live ADB availability
                self.seed_error = str(exc)

    def seed_documents(self) -> None:
        """Create/update the Oracle RAG document table."""
        search_texts = [build_search_text(document) for document in self.documents]
        embeddings = self._embedding_client().embed_documents(search_texts)

        with self.connection_factory() as connection:
            self._ensure_table(connection)
            self._upsert_documents(connection, embeddings)
            connection.commit()

    def retrieve(self, user_question: str) -> list[dict]:
        """Return the most relevant documents for the user question."""
        try:
            query_embedding = self._embedding_client().embed_query(user_question)
            scored_documents = self._search_oracle_vector(query_embedding)
        except Exception:
            scored_documents = []

        if scored_documents:
            return [self._without_score(document) for document in scored_documents]

        return self._local_search(extract_search_terms(user_question))

    def _search_oracle_vector(self, query_embedding: list[float]) -> list[dict]:
        try:
            with self.connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute(
                    self._build_vector_search_sql(),
                    {
                        "query_embedding": self._to_vector_json(query_embedding),
                        "top_k": self.top_k,
                    },
                )
                rows = cursor.fetchall()
        except Exception:
            return []

        return [
            {
                "id": row[0],
                "title": row[1],
                "type": row[2],
                "content": row[3],
                "distance": float(row[4]),
            }
            for row in rows
        ]

    def _local_search(self, search_terms: list[str]) -> list[dict]:
        scored_documents = []
        for document in self.documents:
            search_text = build_search_text(document)
            score = sum(search_text.count(term) for term in search_terms)
            if score > 0:
                scored_documents.append({**document, "score": float(score)})

        scored_documents.sort(key=lambda document: document["score"], reverse=True)
        return [self._without_score(document) for document in scored_documents[: self.top_k]]

    def _ensure_table(self, connection: Any) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM user_tables
                WHERE table_name = :table_name
                """,
                {"table_name": self.table_name.upper()},
            )
            table_exists = cursor.fetchone()[0] > 0

            if table_exists:
                self._ensure_vector_columns(cursor)
                return

            cursor.execute(
                f"""
                CREATE TABLE {self.table_name} (
                    id VARCHAR2(100) PRIMARY KEY,
                    title VARCHAR2(500) NOT NULL,
                    doc_type VARCHAR2(100) NOT NULL,
                    content VARCHAR2(4000) NOT NULL,
                    search_text VARCHAR2(4000) NOT NULL,
                    embedding VECTOR(1024, FLOAT32),
                    embedding_model VARCHAR2(200),
                    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP
                )
                """
            )

    def _ensure_vector_columns(self, cursor: Any) -> None:
        cursor.execute(
            """
            SELECT column_name
            FROM user_tab_columns
            WHERE table_name = :table_name
            """,
            {"table_name": self.table_name.upper()},
        )
        columns = {row[0] for row in cursor.fetchall()}

        if "EMBEDDING" not in columns:
            cursor.execute(f"ALTER TABLE {self.table_name} ADD embedding VECTOR(1024, FLOAT32)")

        if "EMBEDDING_MODEL" not in columns:
            cursor.execute(f"ALTER TABLE {self.table_name} ADD embedding_model VARCHAR2(200)")

    def _upsert_documents(self, connection: Any, embeddings: list[list[float]]) -> None:
        with connection.cursor() as cursor:
            for document, embedding in zip(self.documents, embeddings, strict=True):
                cursor.execute(
                    f"""
                    MERGE INTO {self.table_name} target
                    USING (
                        SELECT
                            :id AS id,
                            :title AS title,
                            :doc_type AS doc_type,
                            :content AS content,
                            :search_text AS search_text,
                            TO_VECTOR(:embedding) AS embedding,
                            :embedding_model AS embedding_model
                        FROM dual
                    ) source
                    ON (target.id = source.id)
                    WHEN MATCHED THEN UPDATE SET
                        target.title = source.title,
                        target.doc_type = source.doc_type,
                        target.content = source.content,
                        target.search_text = source.search_text,
                        target.embedding = source.embedding,
                        target.embedding_model = source.embedding_model,
                        target.updated_at = SYSTIMESTAMP
                    WHEN NOT MATCHED THEN INSERT (
                        id, title, doc_type, content, search_text, embedding, embedding_model
                    ) VALUES (
                        source.id,
                        source.title,
                        source.doc_type,
                        source.content,
                        source.search_text,
                        source.embedding,
                        source.embedding_model
                    )
                    """,
                    {
                        "id": document["id"],
                        "title": document["title"],
                        "doc_type": document["type"],
                        "content": document["content"],
                        "search_text": build_search_text(document),
                        "embedding": self._to_vector_json(embedding),
                        "embedding_model": self._embedding_client().model_id,
                    },
                )

    def _build_vector_search_sql(self) -> str:
        return f"""
            SELECT
                id,
                title,
                doc_type,
                content,
                VECTOR_DISTANCE(embedding, TO_VECTOR(:query_embedding), COSINE) AS distance
            FROM {self.table_name}
            WHERE embedding IS NOT NULL
            ORDER BY distance ASC, id
            FETCH FIRST :top_k ROWS ONLY
        """

    def _to_vector_json(self, embedding: list[float]) -> str:
        return json.dumps(embedding)

    def _embedding_client(self) -> OCITextEmbeddingClient:
        if self.embedding_client is None:
            self.embedding_client = OCITextEmbeddingClient()
        return self.embedding_client

    def _auto_seed_enabled(self) -> bool:
        return os.getenv("RAG_AUTO_SEED_ON_STARTUP", "false").lower() == "true"

    def _without_score(self, document: dict) -> dict:
        return {
            "id": document["id"],
            "title": document["title"],
            "type": document["type"],
            "content": document["content"],
        }


KeywordRetriever = OracleRAGRetriever
