"""Unit tests for the Oracle-backed RAG retriever."""

from __future__ import annotations

from app.rag.retriever import OracleRAGRetriever

DOCUMENTS = [
    {
        "id": "schema_product_sales",
        "title": "Product Sales Dataset Table Description",
        "type": "table_schema",
        "content": "The product_sales table contains sales, category, revenue, and profit rows.",
    },
    {
        "id": "kpi_revenue",
        "title": "Revenue KPI Definition",
        "type": "kpi_definition",
        "content": "Revenue means the total sales amount. Use SUM(Revenue).",
    },
    {
        "id": "kpi_profit",
        "title": "Profit KPI Definition",
        "type": "kpi_definition",
        "content": "Profit means the total profit amount. Use SUM(Profit).",
    },
]


class FakeCursor:
    def __init__(self) -> None:
        self.statement: str | None = None
        self.parameters: dict | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, statement: str, parameters: dict | None = None) -> None:
        self.statement = statement
        self.parameters = parameters or {}

    def fetchall(self) -> list[tuple[str, str, str, str, float]]:
        return [
            (
                "kpi_revenue",
                "Revenue KPI Definition",
                "kpi_definition",
                "Revenue means the total sales amount. Use SUM(Revenue).",
                3.0,
            )
        ]


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


class FakeEmbeddingClient:
    model_id = "fake.embed"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.4]


class FailingEmbeddingClient:
    model_id = "fake.embed"

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("embedding service unavailable")


def test_retrieve_uses_oracle_scored_documents() -> None:
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    retriever = OracleRAGRetriever(
        documents=DOCUMENTS[1:],
        top_k=1,
        connection_factory=lambda: connection,
        embedding_client=FakeEmbeddingClient(),
        auto_seed=False,
    )

    documents = retriever.retrieve("total sales by category")

    assert documents == [DOCUMENTS[1]]
    assert "APP_RAG_DOCUMENTS" in cursor.statement
    assert "VECTOR_DISTANCE" in cursor.statement
    assert cursor.parameters["top_k"] == 1
    assert cursor.parameters["query_embedding"] == "[0.1, 0.2, 0.4]"


def test_retrieve_falls_back_to_local_search_when_oracle_is_unavailable() -> None:
    retriever = OracleRAGRetriever(
        documents=DOCUMENTS[1:],
        top_k=1,
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
        embedding_client=FailingEmbeddingClient(),
        auto_seed=False,
    )

    documents = retriever.retrieve("total profit")

    assert documents == [DOCUMENTS[2]]


def test_retrieve_includes_table_schema_when_only_kpi_matches_locally() -> None:
    retriever = OracleRAGRetriever(
        documents=DOCUMENTS,
        top_k=2,
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
        embedding_client=FailingEmbeddingClient(),
        auto_seed=False,
    )

    documents = retriever.retrieve("total profit")

    assert documents[0]["type"] == "table_schema"
    assert documents[1]["id"] == "kpi_profit"
