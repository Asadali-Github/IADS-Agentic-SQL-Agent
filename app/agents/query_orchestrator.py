"""Query orchestrator agent for the placeholder RAG pipeline."""

from __future__ import annotations

from app.agents.memory import ConversationMemory, MemoryAnswer, QuestionResolution
from app.agents.summariser import SelectAIResultSummariser
from app.agents.support_guard import (
    assess_question_intent_safety,
    assess_question_support,
    unsupported_answer,
)
from app.rag.retriever import OracleRAGRetriever
from app.sql.executor import SafeSQLExecutor
from app.sql.generator import OracleSelectAISQLGenerator
from app.sql.prompt_builder import SQLPromptBuilder
from app.sql.validator import validate_sql


class QueryOrchestrator:
    """Coordinates RAG retrieval, SQL generation, validation, and execution."""

    def __init__(
        self,
        retriever: OracleRAGRetriever | None = None,
        prompt_builder: SQLPromptBuilder | None = None,
        sql_generator: OracleSelectAISQLGenerator | None = None,
        sql_executor: SafeSQLExecutor | None = None,
        summariser: SelectAIResultSummariser | None = None,
        memory: ConversationMemory | None = None,
    ) -> None:
        self.retriever = retriever or OracleRAGRetriever()
        self.prompt_builder = prompt_builder or SQLPromptBuilder()
        self.sql_generator = sql_generator or OracleSelectAISQLGenerator()
        self.sql_executor = sql_executor or SafeSQLExecutor()
        self.summariser = summariser or SelectAIResultSummariser()
        self.memory = memory or ConversationMemory()

    def process_question(self, user_question: str) -> dict:
        """Run the RAG-to-Select-AI-to-results pipeline for a user question."""
        intent_assessment = assess_question_intent_safety(user_question)
        if not intent_assessment["is_supported"]:
            response = self._unsupported_response(
                user_question=user_question,
                resolved_question=user_question.strip(),
                retrieved_documents=[],
                support_assessment=intent_assessment,
                retrieval_provider="not_run_safety_guard",
            )
            self.memory.record(response)
            return response

        resolution = self.memory.resolve(user_question)
        memory_answer = self.memory.answer_from_previous_results(user_question)
        if memory_answer:
            response = self._memory_answer_response(user_question, resolution, memory_answer)
            self.memory.record(response)
            return response

        resolved_question = resolution.resolved_question
        retrieved_documents = self.retriever.retrieve(resolution.retrieval_question)
        support_assessment = assess_question_support(
            resolution.support_question,
            retrieved_documents,
        )
        if not support_assessment["is_supported"]:
            response = self._unsupported_response(
                user_question=user_question,
                resolved_question=resolved_question,
                retrieved_documents=retrieved_documents,
                support_assessment=support_assessment,
            )
            self.memory.record(response)
            return response

        sql_generation_prompt = self.prompt_builder.build_prompt(
            user_question=resolved_question,
            retrieved_documents=retrieved_documents,
            conversation_context=resolution.conversation_context,
        )
        generated_sql = self.sql_generator.generate(sql_generation_prompt)
        sql_validation = validate_sql(generated_sql["sql"])
        query_results = self.sql_executor.execute(sql_validation)
        answer = self.summariser.summarise(resolved_question, generated_sql, query_results)

        response = {
            "original_question": user_question,
            "resolved_question": resolved_question,
            "retrieved_documents": retrieved_documents,
            "retrieval_provider": getattr(self.retriever, "last_retrieval_provider", None),
            "retrieval_error": getattr(self.retriever, "last_retrieval_error", None),
            "support_assessment": support_assessment,
            "sql_generation_prompt": sql_generation_prompt,
            "generated_sql": generated_sql,
            "sql_validation": sql_validation,
            "query_results": query_results,
            "answer": answer,
            "pipeline_stage": self._pipeline_stage(generated_sql, sql_validation, query_results),
        }
        self.memory.record(response)
        return response

    def _unsupported_response(
        self,
        user_question: str,
        resolved_question: str,
        retrieved_documents: list[dict],
        support_assessment: dict,
        retrieval_provider: str | None = None,
    ) -> dict:
        sql_validation = validate_sql(None)
        query_results = self.sql_executor.execute(sql_validation)
        return {
            "original_question": user_question,
            "resolved_question": resolved_question,
            "retrieved_documents": retrieved_documents,
            "retrieval_provider": retrieval_provider
            or getattr(self.retriever, "last_retrieval_provider", None),
            "retrieval_error": getattr(self.retriever, "last_retrieval_error", None),
            "support_assessment": support_assessment,
            "sql_generation_prompt": None,
            "generated_sql": {
                "sql": None,
                "clarification_question": None,
                "reasoning": (
                    "SQL generation skipped because the retrieved context was unsupported."
                ),
                "provider": "local_no_answer",
                "error": None,
            },
            "sql_validation": sql_validation,
            "query_results": query_results,
            "answer": unsupported_answer(support_assessment["reason"]),
            "pipeline_stage": "unsupported_question_no_sql_generated",
        }

    def _memory_answer_response(
        self,
        user_question: str,
        resolution: QuestionResolution,
        memory_answer: MemoryAnswer,
    ) -> dict:
        source_sql = memory_answer.source_turn.generated_sql.get("sql")
        sql_validation = validate_sql(source_sql)
        query_results = {
            "status": "success",
            "reason": "Answered from previous result rows; no new SQL execution was needed.",
            "sql": source_sql,
            "columns": memory_answer.columns,
            "rows": memory_answer.rows,
            "row_count": len(memory_answer.rows),
            "row_limit": len(memory_answer.source_turn.query_results.get("rows") or []),
            "error": None,
        }
        return {
            "original_question": user_question,
            "resolved_question": resolution.resolved_question,
            "retrieved_documents": memory_answer.source_turn.retrieved_documents,
            "retrieval_provider": "conversation_memory",
            "retrieval_error": None,
            "support_assessment": {
                "is_supported": True,
                "reason": "Answered from previous result rows in conversation memory.",
                "matched_terms": [],
            },
            "sql_generation_prompt": None,
            "generated_sql": {
                "sql": source_sql,
                "clarification_question": None,
                "reasoning": (
                    "No new SQL was generated because the question referred to the "
                    "previous result table."
                ),
                "provider": "conversation_memory",
                "error": None,
            },
            "sql_validation": sql_validation,
            "query_results": query_results,
            "answer": {
                "answer": memory_answer.answer,
                "provider": "conversation_memory",
                "prompt_row_count": len(memory_answer.rows),
                "error": None,
            },
            "pipeline_stage": "answered_from_conversation_memory",
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
        if query_results["status"] == "fallback_success":
            return "sql_executed_with_fallback"
        if query_results["status"] != "success":
            return "sql_validated_but_execution_failed"
        return "sql_executed_successfully"
