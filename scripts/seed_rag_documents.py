"""Seed Oracle vector RAG documents from placeholder_docs.json."""

from __future__ import annotations

from dotenv import load_dotenv

from app.rag.retriever import OracleRAGRetriever


def main() -> None:
    load_dotenv()
    retriever = OracleRAGRetriever(auto_seed=False)
    retriever.seed_documents()
    print("Oracle RAG documents seeded into APP_RAG_DOCUMENTS.")


if __name__ == "__main__":
    main()
