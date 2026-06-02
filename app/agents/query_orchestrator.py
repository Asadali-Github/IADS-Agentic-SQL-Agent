"""Query orchestrator agent for the placeholder RAG pipeline."""

from __future__ import annotations

from app.rag.retriever import LangChainRAGRetriever
from app.sql.prompt_builder import SQLPromptBuilder


class QueryOrchestrator:
    """Coordinates RAG retrieval and SQL prompt preparation."""

    def __init__(
        self,
        retriever: LangChainRAGRetriever | None = None,
        prompt_builder: SQLPromptBuilder | None = None,
    ) -> None:
        self.retriever = retriever or LangChainRAGRetriever()
        self.prompt_builder = prompt_builder or SQLPromptBuilder()

    def process_question(self, user_question: str) -> dict:
        """Run the first-stage agentic pipeline for a user question."""
        retrieved_documents = self.retriever.retrieve(user_question)
        sql_generation_prompt = self.prompt_builder.build_prompt(
            user_question=user_question,
            retrieved_documents=retrieved_documents,
        )

        return {
            "original_question": user_question,
            "retrieved_documents": retrieved_documents,
            "sql_generation_prompt": sql_generation_prompt,
            "pipeline_stage": "rag_context_prepared_for_future_sql_generation",
        }
