"""Query orchestrator agent for the placeholder RAG pipeline."""

from __future__ import annotations

from app.agents.action_decider import QueryActionDecider
from app.agents.followup_suggester import FollowUpSuggester
from app.agents.memory import ConversationMemory, MemoryAnswer, QuestionResolution
from app.agents.planner import QueryPlanner
from app.agents.reflector import QueryReflector
from app.agents.result_transformer import CachedResultTransformer
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
        planner: QueryPlanner | None = None,
        reflector: QueryReflector | None = None,
        action_decider: QueryActionDecider | None = None,
        followup_suggester: FollowUpSuggester | None = None,
    ) -> None:
        self.retriever = retriever or OracleRAGRetriever()
        self.prompt_builder = prompt_builder or SQLPromptBuilder()
        self.sql_generator = sql_generator or OracleSelectAISQLGenerator()
        self.sql_executor = sql_executor or SafeSQLExecutor()
        self.summariser = summariser or SelectAIResultSummariser()
        self.memory = memory or ConversationMemory()
        self.planner = planner or QueryPlanner()
        self.reflector = reflector or QueryReflector()
        self.action_decider = action_decider or QueryActionDecider()
        self.followup_suggester = followup_suggester or FollowUpSuggester()
        self.result_transformer = CachedResultTransformer(self.memory)

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
                action_decision=None,
            )
            self.memory.record(response)
            return response

        action_decision = self.action_decider.decide_next_action(
            user_question,
            self._conversation_state(),
        )
        if action_decision["action"] == "ASK_CLARIFICATION":
            response = self._clarification_response(user_question, action_decision)
            self.memory.record(response)
            return response

        if action_decision["action"] == "TRANSFORM_PREVIOUS_RESULT":
            memory_answer = self.result_transformer.transform(user_question)
            if not memory_answer:
                response = self._clarification_response(
                    user_question,
                    {
                        **action_decision,
                        "reason": (
                            "I could not safely transform the previous result. "
                            "Please specify the column, filter, or format you want."
                        ),
                    },
                )
                self.memory.record(response)
                return response

            resolution = QuestionResolution(
                original_question=user_question.strip(),
                resolved_question=user_question.strip(),
                retrieval_question=user_question.strip(),
                is_follow_up=True,
            )
            response = self._memory_answer_response(
                user_question,
                resolution,
                memory_answer,
                action_decision,
            )
            self.memory.record(response)
            return response

        resolution = self._resolve_for_action(user_question, action_decision)
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
                action_decision=action_decision,
            )
            self.memory.record(response)
            return response

        plan = self.planner.plan(resolved_question, retrieved_documents)
        sql_generation_prompt = self.prompt_builder.build_prompt(
            user_question=resolved_question,
            retrieved_documents=retrieved_documents,
            conversation_context=resolution.conversation_context,
        )
        generated_sql = self.sql_generator.generate(sql_generation_prompt)
        sql_validation = validate_sql(generated_sql["sql"])
        query_results = self.sql_executor.execute(sql_validation)
        reflection = self.reflector.reflect(
            question=resolved_question,
            generated_sql=generated_sql,
            query_results=query_results,
            retrieved_documents=retrieved_documents,
        )
        if not reflection["ok"] and reflection.get("corrected_sql"):
            corrected_sql = reflection["corrected_sql"]
            sql_validation = validate_sql(corrected_sql)
            query_results = self.sql_executor.execute(sql_validation)
            generated_sql = {
                **generated_sql,
                "sql": corrected_sql,
                "reasoning": (
                    f"{generated_sql.get('reasoning') or ''} "
                    "[Reflector correction applied]"
                ).strip(),
            }
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
            "plan": plan,
            "reflection": reflection,
            "action_decision": action_decision,
            "answer": answer,
            "pipeline_stage": self._pipeline_stage(generated_sql, sql_validation, query_results),
        }
        response["suggestions"] = self.followup_suggester.suggest(response)
        self.memory.record(response)
        return response

    def _unsupported_response(
        self,
        user_question: str,
        resolved_question: str,
        retrieved_documents: list[dict],
        support_assessment: dict,
        retrieval_provider: str | None = None,
        action_decision: dict | None = None,
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
            "plan": None,
            "reflection": None,
            "action_decision": action_decision,
            "answer": unsupported_answer(support_assessment["reason"]),
            "pipeline_stage": "unsupported_question_no_sql_generated",
        }

    def _clarification_response(self, user_question: str, action_decision: dict) -> dict:
        sql_validation = validate_sql(None)
        query_results = {
            "status": "skipped",
            "reason": "SQL was not executed because the action decision asked for clarification.",
            "sql": None,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "row_limit": 0,
            "error": None,
        }
        return {
            "original_question": user_question,
            "resolved_question": user_question.strip(),
            "retrieved_documents": [],
            "retrieval_provider": "not_run_action_decider",
            "retrieval_error": None,
            "support_assessment": {
                "is_supported": True,
                "reason": "Action decision requested clarification.",
                "matched_terms": [],
            },
            "sql_generation_prompt": None,
            "generated_sql": {
                "sql": None,
                "clarification_question": (
                    "Do you want me to use the previous result, modify the previous SQL, "
                    "or run a new query?"
                ),
                "reasoning": "SQL generation skipped by action decision.",
                "provider": "action_decider",
                "error": None,
            },
            "sql_validation": sql_validation,
            "query_results": query_results,
            "plan": None,
            "reflection": None,
            "action_decision": action_decision,
            "answer": {
                "answer": action_decision.get("reason") or "I need clarification.",
                "provider": "action_decider",
                "prompt_row_count": 0,
                "error": None,
            },
            "pipeline_stage": "action_decision_asked_clarification",
        }

    def _memory_answer_response(
        self,
        user_question: str,
        resolution: QuestionResolution,
        memory_answer: MemoryAnswer,
        action_decision: dict | None = None,
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
            "plan": None,
            "reflection": None,
            "action_decision": action_decision,
            "answer": {
                "answer": memory_answer.answer,
                "provider": "conversation_memory",
                "prompt_row_count": len(memory_answer.rows),
                "error": None,
            },
            "pipeline_stage": "answered_from_conversation_memory",
        }

    def _conversation_state(self) -> dict:
        latest_result = self.memory.latest_result_turn()
        latest_successful = self.memory.latest_successful_turn()
        return {
            "has_previous_result": latest_result is not None,
            "has_previous_sql": latest_successful is not None
            and bool(latest_successful.generated_sql.get("sql")),
            "last_question": latest_successful.original_question if latest_successful else None,
            "last_sql": latest_successful.generated_sql.get("sql") if latest_successful else None,
            "last_columns": latest_result.query_results.get("columns") if latest_result else [],
            "last_row_count": latest_result.query_results.get("row_count") if latest_result else 0,
        }

    def _resolve_for_action(self, user_question: str, action_decision: dict) -> QuestionResolution:
        if action_decision["action"] == "MODIFY_PREVIOUS_SQL":
            displayed_entity_resolution = self.memory.resolve_displayed_entity_reference(
                user_question
            )
            if displayed_entity_resolution:
                return displayed_entity_resolution

            resolution = self.memory.resolve(user_question)
            if resolution.is_follow_up:
                return resolution

            previous_turn = self.memory.latest_successful_turn()
            if previous_turn:
                question = user_question.strip()
                conversation_context = (
                    f"Previous successful question: {previous_turn.original_question}\n"
                    f"Previous SQL: {previous_turn.generated_sql.get('sql')}\n"
                    "Use the previous filters, grouping, and business scope unless the "
                    "follow-up explicitly changes them."
                )
                return QuestionResolution(
                    original_question=question,
                    resolved_question=(
                        f"{question} "
                        f"(same business context as previous question: "
                        f"{previous_turn.original_question})"
                    ),
                    retrieval_question=f"{previous_turn.original_question} {question}",
                    is_follow_up=True,
                    conversation_context=conversation_context,
                )

            return resolution
        question = user_question.strip()
        return QuestionResolution(
            original_question=question,
            resolved_question=question,
            retrieval_question=question,
            is_follow_up=False,
        )

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
