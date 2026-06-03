"""Query orchestrator agent for the placeholder RAG pipeline."""

from __future__ import annotations

from app.rag.retriever import LangChainRAGRetriever
from app.sql.generator import OracleSelectAISQLGenerator
from app.sql.prompt_builder import SQLPromptBuilder


class QueryOrchestrator:
    """Coordinates RAG retrieval, SQL prompt preparation, and SQL generation."""

    def __init__(
        self,
        retriever: LangChainRAGRetriever | None = None,
        prompt_builder: SQLPromptBuilder | None = None,
        sql_generator: OracleSelectAISQLGenerator | None = None,
    ) -> None:
        self.retriever = retriever or LangChainRAGRetriever()
        self.prompt_builder = prompt_builder or SQLPromptBuilder()
        self.sql_generator = sql_generator or OracleSelectAISQLGenerator()

    def process_question(self, user_question: str) -> dict:
        """Run the RAG-to-Select-AI SQL generation pipeline for a user question."""
        retrieved_documents = self.retriever.retrieve(user_question)
        sql_generation_prompt = self.prompt_builder.build_prompt(
            user_question=user_question,
            retrieved_documents=retrieved_documents,
        )
        generated_sql = self.sql_generator.generate(sql_generation_prompt)

        return {
            "original_question": user_question,
            "retrieved_documents": retrieved_documents,
            "sql_generation_prompt": sql_generation_prompt,
            "generated_sql": generated_sql,
            "pipeline_stage": "sql_generated_with_oracle_select_ai"
            if generated_sql["sql"]
            else "rag_context_prepared_for_select_ai_sql_generation",
        }
