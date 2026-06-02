"""Load placeholder RAG documents for the prototype."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.documents import Document


DEFAULT_DOCS_PATH = Path(__file__).resolve().parents[2] / "data" / "placeholder_docs.json"


def load_documents(file_path: Path | None = None) -> list[dict]:
    """Load placeholder documents from JSON."""
    docs_path = file_path or DEFAULT_DOCS_PATH

    with docs_path.open("r", encoding="utf-8") as file:
        documents = json.load(file)

    if not isinstance(documents, list):
        raise ValueError("placeholder_docs.json must contain a list of documents.")

    for document in documents:
        required_fields = {"id", "title", "type", "content"}
        missing_fields = required_fields - set(document)
        if missing_fields:
            raise ValueError(
                f"Document {document.get('id', '<unknown>')} is missing: {missing_fields}"
            )

    return documents


def load_langchain_documents(file_path: Path | None = None) -> list[Document]:
    """Load placeholder documents in LangChain's standard Document format."""
    documents = load_documents(file_path)

    return [
        Document(
            id=document["id"],
            page_content=document["content"],
            metadata={
                "id": document["id"],
                "title": document["title"],
                "type": document["type"],
            },
        )
        for document in documents
    ]
