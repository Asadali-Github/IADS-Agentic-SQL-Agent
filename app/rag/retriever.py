"""LangChain-based retriever for placeholder RAG documents."""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore

from app.rag.documents import load_langchain_documents
from app.rag.embeddings import LocalKeywordEmbeddings


class LangChainRAGRetriever:
    """Retrieves relevant documents using LangChain's vector store interface."""

    def __init__(
        self,
        documents: list[Document] | None = None,
        top_k: int = 4,
        min_relevance_ratio: float = 0.3,
    ) -> None:
        self.documents = documents or load_langchain_documents()
        self.top_k = top_k
        self.min_relevance_ratio = min_relevance_ratio
        self.embeddings = LocalKeywordEmbeddings(
            [self._document_search_text(document) for document in self.documents]
        )
        self.vector_store = InMemoryVectorStore(self.embeddings)
        searchable_documents = [self._to_searchable_document(document) for document in self.documents]
        self.vector_store.add_documents(
            documents=searchable_documents,
            ids=[document.metadata["id"] for document in searchable_documents],
        )

    def retrieve(self, user_question: str) -> list[dict]:
        """Return the most relevant documents for the user question."""
        scored_documents = self.vector_store.similarity_search_with_score(
            query=user_question,
            k=self.top_k,
        )
        if not scored_documents:
            return []

        minimum_score = scored_documents[0][1] * self.min_relevance_ratio
        retrieved_documents = [
            document for document, score in scored_documents if score >= minimum_score
        ]

        return [self._to_plain_document(document) for document in retrieved_documents]

    def _document_search_text(self, document: Document) -> str:
        metadata = document.metadata
        return " ".join(
            [
                metadata["title"],
                metadata["type"],
                document.page_content,
            ]
        )

    def _to_plain_document(self, document: Document) -> dict:
        return {
            "id": document.metadata["id"],
            "title": document.metadata["title"],
            "type": document.metadata["type"],
            "content": document.metadata["content"],
        }

    def _to_searchable_document(self, document: Document) -> Document:
        return Document(
            id=document.id,
            page_content=self._document_search_text(document),
            metadata={
                **document.metadata,
                "content": document.page_content,
            },
        )


KeywordRetriever = LangChainRAGRetriever
