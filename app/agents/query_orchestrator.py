"""Query orchestrator agent for the placeholder RAG pipeline."""

from __future__ import annotations

from app.agents.summariser import SelectAIResultSummariser
from app.rag.retriever import LangChainRAGRetriever
from app.sql.executor import SafeSQLExecutor
from app.sql.generator import OracleSelectAISQLGenerator
from app.sql.prompt_builder import SQLPromptBuilder
from app.sql.validator import validate_sql


class QueryOrchestrator:
    """Coordinates RAG retrieval, SQL generation, validation, and execution."""

    def __init__(
        self,
        retriever: LangChainRAGRetriever | None = None,
        prompt_builder: SQLPromptBuilder | None = None,
        sql_generator: OracleSelectAISQLGenerator | None = None,
        sql_executor: SafeSQLExecutor | None = None,
        summariser: SelectAIResultSummariser | None = None,
    ) -> None:
        self.retriever = retriever or LangChainRAGRetriever()
        self.prompt_builder = prompt_builder or SQLPromptBuilder()
        self.sql_generator = sql_generator or OracleSelectAISQLGenerator()
        self.sql_executor = sql_executor or SafeSQLExecutor()
        self.summariser = summariser or SelectAIResultSummariser()

    def process_question(self, user_question: str) -> dict:
        """Run the RAG-to-Select-AI-to-results pipeline for a user question."""
        retrieved_documents = self.retriever.retrieve(user_question)
        sql_generation_prompt = self.prompt_builder.build_prompt(
            user_question=user_question,
            retrieved_documents=retrieved_documents,
        )
        generated_sql = self.sql_generator.generate(sql_generation_prompt)
        sql_validation = validate_sql(generated_sql["sql"])
        query_results = self.sql_executor.execute(sql_validation)
        answer = self.summariser.summarise(user_question, generated_sql, query_results)

        return {
            "original_question": user_question,
            "retrieved_documents": retrieved_documents,
            "sql_generation_prompt": sql_generation_prompt,
            "generated_sql": generated_sql,
            "sql_validation": sql_validation,
            "query_results": query_results,
            "answer": answer,
            "pipeline_stage": self._pipeline_stage(generated_sql, sql_validation, query_results),
        }

    def _pipeline_stage(
        self,
        generated_sql: dict,
        sql_validation: dict,
        query_results: dict,
    ) -> str:
        if not generated_sql["sql"]:
            return "rag_context_prepared_for_select_ai_sql_generation"
        if not sql_validation["is_valid"]:
            return "sql_generated_but_validation_failed"
        if query_results["status"] != "success":
            return "sql_validated_but_execution_failed"
        return "sql_executed_successfully"
