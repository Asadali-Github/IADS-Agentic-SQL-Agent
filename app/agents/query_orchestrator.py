"""Query orchestrator agent for the placeholder RAG pipeline."""

from __future__ import annotations

from app.rag.retriever import LangChainRAGRetriever
from app.sql.executor import OracleSQLExecutor
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
        sql_executor: OracleSQLExecutor | None = None,
    ) -> None:
        self.retriever = retriever or LangChainRAGRetriever()
        self.prompt_builder = prompt_builder or SQLPromptBuilder()
        self.sql_generator = sql_generator or OracleSelectAISQLGenerator()
        self.sql_executor = sql_executor or OracleSQLExecutor()

    def process_question(self, user_question: str) -> dict:
        """Run the RAG-to-Select-AI-to-Oracle execution pipeline."""
        retrieved_documents = self.retriever.retrieve(user_question)
        sql_generation_prompt = self.prompt_builder.build_prompt(
            user_question=user_question,
            retrieved_documents=retrieved_documents,
        )
        generated_sql = self.sql_generator.generate(sql_generation_prompt)
        sql_text = generated_sql["sql"] or ""
        validation_result = (
            validate_sql(sql_text)
            if sql_text
            else {
                "is_valid": False,
                "reason": "SQL generation failed or returned no SQL.",
            }
        )
        execution_result = {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "capped": False,
            "error": "Execution skipped because SQL generation did not return SQL."
            if not sql_text
            else None,
        }

        if sql_text and validation_result["is_valid"]:
            execution_result = self.sql_executor.execute(sql_text)

        return {
            "original_question": user_question,
            "retrieved_documents": retrieved_documents,
            "sql_generation_prompt": sql_generation_prompt,
            "generated_sql": generated_sql,
            "validation_result": validation_result,
            "execution_result": execution_result,
            "pipeline_stage": self._pipeline_stage(
                generated_sql=generated_sql,
                validation_result=validation_result,
                execution_result=execution_result,
            ),
        }

    def _pipeline_stage(
        self,
        generated_sql: dict,
        validation_result: dict,
        execution_result: dict,
    ) -> str:
        if not generated_sql["sql"]:
            return "rag_context_prepared_for_select_ai_sql_generation"

        if not validation_result["is_valid"]:
            return "sql_generated_but_validation_failed"

        if execution_result["success"]:
            return "sql_validated_and_executed_against_oracle"

        return "sql_validated_but_execution_failed"
