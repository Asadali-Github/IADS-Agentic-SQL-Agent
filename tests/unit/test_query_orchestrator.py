"""Unit tests for conversation memory and unsupported-question guardrails."""

from __future__ import annotations

from typing import Any

from app.agents.query_orchestrator import QueryOrchestrator
from app.sql.executor import SafeSQLExecutor

REVENUE_DOC = {
    "id": "kpi_revenue",
    "title": "Revenue KPI Definition",
    "type": "kpi_definition",
    "content": "Revenue means total sales. Use SUM(Revenue) by Category.",
}

PROFIT_DOC = {
    "id": "kpi_profit",
    "title": "Profit KPI Definition",
    "type": "kpi_definition",
    "content": "Profit means total profit. Use SUM(Profit) by Category.",
}

CUSTOMER_DOC = {
    "id": "schema_customer",
    "title": "Customer Schema",
    "type": "schema_knowledge",
    "content": "Customer names are stored in CUSTOMER_NAME. Use customer filters for names.",
}


class FakeRetriever:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self.questions: list[str] = []

    def retrieve(self, user_question: str) -> list[dict]:
        self.questions.append(user_question)
        return self.documents


class FakeGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> dict[str, Any]:
        self.prompts.append(prompt)
        return {
            "sql": 'SELECT "CATEGORY", SUM("REVENUE") AS total_sales FROM product_sales',
            "clarification_question": None,
            "reasoning": "fake",
            "provider": "fake",
            "error": None,
        }


class FakeProductGenerator:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> dict[str, Any]:
        self.prompts.append(prompt)
        return {
            "sql": (
                'SELECT "PRODUCT_NAME", SUM("REVENUE") AS total_revenue '
                'FROM "ADMIN"."PRODUCT_SALES_DATASET_FINAL" '
                'GROUP BY "PRODUCT_NAME" '
                'ORDER BY total_revenue DESC FETCH FIRST 5 ROWS ONLY'
            ),
            "clarification_question": None,
            "reasoning": "fake product SQL",
            "provider": "fake",
            "error": None,
        }


class FailingGenerator:
    def generate(self, prompt: str) -> dict[str, Any]:
        raise AssertionError("Generator should not be called for unsupported questions.")


class FakeExecutor:
    def execute(self, sql_validation: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "reason": "fake execution",
            "sql": sql_validation.get("safe_sql"),
            "columns": ["CATEGORY", "TOTAL_SALES"],
            "rows": [{"CATEGORY": "Electronics", "TOTAL_SALES": 10}],
            "row_count": 1,
            "row_limit": 100,
            "error": None,
        }


class FakeProductExecutor:
    def __init__(self) -> None:
        self.execution_count = 0

    def execute(self, sql_validation: dict[str, Any]) -> dict[str, Any]:
        self.execution_count += 1
        return {
            "status": "success",
            "reason": "fake execution",
            "sql": sql_validation.get("safe_sql"),
            "columns": ["PRODUCT_NAME", "TOTAL_REVENUE"],
            "rows": [
                {"PRODUCT_NAME": "Tempur-Pedic Mattress", "TOTAL_REVENUE": 9061755.86},
                {"PRODUCT_NAME": "Instant Pot", "TOTAL_REVENUE": 8903475.26},
                {"PRODUCT_NAME": "MacBook Air", "TOTAL_REVENUE": 7362516.81},
                {"PRODUCT_NAME": "Apple Watch", "TOTAL_REVENUE": 6834472.35},
                {"PRODUCT_NAME": "Apple iPhone 14", "TOTAL_REVENUE": 5740819.18},
            ],
            "row_count": 5,
            "row_limit": 100,
            "error": None,
        }


class FakeCustomerExecutor:
    def __init__(self) -> None:
        self.execution_count = 0

    def execute(self, sql_validation: dict[str, Any]) -> dict[str, Any]:
        self.execution_count += 1
        return {
            "status": "success",
            "reason": "fake execution",
            "sql": sql_validation.get("safe_sql"),
            "columns": ["CUSTOMER_NAME"],
            "rows": [
                {"CUSTOMER_NAME": "Carol Adams"},
                {"CUSTOMER_NAME": "Cameron Dixon"},
                {"CUSTOMER_NAME": "Casey Dixon"},
                {"CUSTOMER_NAME": "Catherine Reed"},
            ],
            "row_count": 4,
            "row_limit": 100,
            "error": None,
        }


class FakeSummariser:
    def summarise(
        self,
        user_question: str,
        generated_sql: dict[str, Any],
        query_results: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "answer": f"Answered: {user_question}",
            "provider": "fake",
            "prompt_row_count": 1,
            "error": None,
        }


def test_orchestrator_resolves_follow_up_with_previous_successful_question() -> None:
    retriever = FakeRetriever([REVENUE_DOC, PROFIT_DOC])
    generator = FakeGenerator()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=FakeExecutor(),
        summariser=FakeSummariser(),
    )

    first_response = orchestrator.process_question("What were total sales by product category?")
    second_response = orchestrator.process_question("What about profit?")

    assert first_response["pipeline_stage"] == "sql_executed_successfully"
    assert second_response["pipeline_stage"] == "sql_executed_successfully"
    assert second_response["resolved_question"] == "What were total profit by product category?"
    assert retriever.questions[-1] == (
        "What were total sales by product category? What about profit?"
    )
    assert generator.prompts[-1].count("Previous successful question") == 1
    assert "Previous SQL:" in generator.prompts[-1]


def test_orchestrator_does_not_treat_short_non_business_text_as_follow_up() -> None:
    retriever = FakeRetriever([REVENUE_DOC, PROFIT_DOC])
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=FakeGenerator(),
        sql_executor=FakeExecutor(),
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("What were total sales by product category?")
    response = orchestrator.process_question("Thanks")

    assert response["resolved_question"] == "Thanks"
    assert retriever.questions[-1] == "Thanks"


def test_orchestrator_answers_lowest_of_previous_rows_from_memory() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeGenerator()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=FakeProductExecutor(),
        summariser=FakeSummariser(),
    )

    first_response = orchestrator.process_question("What are the top 5 products by revenue?")
    second_response = orchestrator.process_question("what is the lowest of them")

    assert first_response["pipeline_stage"] == "sql_executed_successfully"
    assert second_response["pipeline_stage"] == "answered_from_conversation_memory"
    assert second_response["answer"]["provider"] == "conversation_memory"
    assert "Apple iPhone 14" in second_response["answer"]["answer"]
    assert "5,740,819.18" in second_response["answer"]["answer"]
    assert second_response["query_results"]["rows"] == [
        {"PRODUCT_NAME": "Apple iPhone 14", "TOTAL_REVENUE": 5740819.18}
    ]
    assert len(generator.prompts) == 1
    assert len(retriever.questions) == 1


def test_orchestrator_sorts_previous_rows_without_requerying_database() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    executor = FakeProductExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    first_response = orchestrator.process_question("What are the top 5 products by revenue?")
    sorted_response = orchestrator.process_question("sort them ascendingly")

    assert first_response["pipeline_stage"] == "sql_executed_successfully"
    assert sorted_response["action_decision"]["action"] == "TRANSFORM_PREVIOUS_RESULT"
    assert sorted_response["pipeline_stage"] == "answered_from_conversation_memory"
    assert sorted_response["retrieval_provider"] == "conversation_memory"
    assert sorted_response["query_results"]["rows"] == [
        {"PRODUCT_NAME": "Apple iPhone 14", "TOTAL_REVENUE": 5740819.18},
        {"PRODUCT_NAME": "Apple Watch", "TOTAL_REVENUE": 6834472.35},
        {"PRODUCT_NAME": "MacBook Air", "TOTAL_REVENUE": 7362516.81},
        {"PRODUCT_NAME": "Instant Pot", "TOTAL_REVENUE": 8903475.26},
        {"PRODUCT_NAME": "Tempur-Pedic Mattress", "TOTAL_REVENUE": 9061755.86},
    ]
    assert "sorted ascending by total revenue" in sorted_response["answer"]["answer"]
    assert len(generator.prompts) == 1
    assert len(retriever.questions) == 1
    assert executor.execution_count == 1


def test_standalone_again_question_does_not_keep_previous_sort_context() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=FakeProductExecutor(),
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("What are the top 5 products by revenue?")
    orchestrator.process_question("sort them ascendingly")
    repeated_response = orchestrator.process_question("top 5 products by revenue again")
    sorted_repeated_response = orchestrator.process_question("sort your last answer ascendingly")

    assert repeated_response["pipeline_stage"] == "sql_executed_successfully"
    assert repeated_response["resolved_question"] == "top 5 products by revenue again"
    assert "No prior conversation context." in generator.prompts[-1]
    assert len(generator.prompts) == 2
    assert len(retriever.questions) == 2
    assert sorted_repeated_response["pipeline_stage"] == "answered_from_conversation_memory"
    assert sorted_repeated_response["query_results"]["rows"][0] == {
        "PRODUCT_NAME": "Apple iPhone 14",
        "TOTAL_REVENUE": 5740819.18,
    }


def test_profit_margin_follow_up_rewrites_to_total_metric_by_same_grouping() -> None:
    retriever = FakeRetriever([REVENUE_DOC, PROFIT_DOC])
    generator = FakeGenerator()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=FakeExecutor(),
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("What is profit margin percentage by region?")
    response = orchestrator.process_question("What about revenue?")

    assert response["resolved_question"] == "What is total revenue by region?"
    assert "What is total revenue by region?" in generator.prompts[-1]
    assert "revenue margin" not in response["resolved_question"].lower()


def test_orchestrator_runs_new_sql_for_new_customer_question() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    executor = FakeProductExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    response = orchestrator.process_question("Show top customers by revenue")

    assert response["action_decision"]["action"] == "RUN_NEW_SQL"
    assert response["pipeline_stage"] == "sql_executed_successfully"
    assert len(generator.prompts) == 1
    assert executor.execution_count == 1


def test_orchestrator_modifies_previous_sql_for_year_constraint() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    executor = FakeProductExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("List the top five products by revenue")
    response = orchestrator.process_question("For 2024 only")

    assert response["action_decision"]["action"] == "MODIFY_PREVIOUS_SQL"
    assert response["pipeline_stage"] == "sql_executed_successfully"
    assert "Previous SQL:" in generator.prompts[-1]
    assert executor.execution_count == 2


def test_orchestrator_refresh_executes_sql_instead_of_reusing_cached_rows() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    executor = FakeProductExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("List the top five products by revenue")
    response = orchestrator.process_question("Refresh the result")

    assert response["action_decision"]["action"] == "MODIFY_PREVIOUS_SQL"
    assert response["pipeline_stage"] == "sql_executed_successfully"
    assert len(generator.prompts) == 2
    assert executor.execution_count == 2


def test_orchestrator_explains_previous_result_without_database_call() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    executor = FakeProductExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("List the top five products by revenue")
    response = orchestrator.process_question("Explain this")

    assert response["action_decision"]["action"] == "TRANSFORM_PREVIOUS_RESULT"
    assert response["pipeline_stage"] == "answered_from_conversation_memory"
    assert "previous result contains" in response["answer"]["answer"].lower()
    assert len(generator.prompts) == 1
    assert executor.execution_count == 1


def test_orchestrator_does_not_answer_bare_modify_after_clarification() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    executor = FakeProductExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    first_response = orchestrator.process_question("sort ascendingly")
    second_response = orchestrator.process_question("modify the previous sql")

    assert first_response["action_decision"]["action"] == "ASK_CLARIFICATION"
    assert second_response["action_decision"]["action"] == "ASK_CLARIFICATION"
    assert second_response["pipeline_stage"] == "action_decision_asked_clarification"
    assert len(generator.prompts) == 0
    assert executor.execution_count == 0


def test_orchestrator_does_not_answer_bare_use_previous_result_after_clarification() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    executor = FakeProductExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    first_response = orchestrator.process_question("sort ascendingly")
    second_response = orchestrator.process_question("use previous result")

    assert first_response["action_decision"]["action"] == "ASK_CLARIFICATION"
    assert second_response["action_decision"]["action"] == "ASK_CLARIFICATION"
    assert second_response["pipeline_stage"] == "action_decision_asked_clarification"
    assert "No previous result" in second_response["answer"]["answer"]
    assert len(generator.prompts) == 0
    assert executor.execution_count == 0


def test_orchestrator_binds_this_product_to_latest_displayed_single_row() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeProductGenerator()
    executor = FakeProductExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("List the top five products by revenue")
    lowest_response = orchestrator.process_question("what is the lowest of them")
    compare_response = orchestrator.process_question(
        "compare for this product in 2022, 2023 and 2024"
    )

    assert lowest_response["pipeline_stage"] == "answered_from_conversation_memory"
    assert compare_response["action_decision"]["action"] == "MODIFY_PREVIOUS_SQL"
    assert compare_response["pipeline_stage"] == "sql_executed_successfully"
    assert "Apple iPhone 14" in compare_response["resolved_question"]
    assert "PRODUCT_NAME" in generator.prompts[-1]
    assert "Apple iPhone 14" in generator.prompts[-1]
    assert "Resolved entity reference" in generator.prompts[-1]
    assert executor.execution_count == 2


def test_orchestrator_filters_previous_rows_by_text_without_requerying() -> None:
    retriever = FakeRetriever([CUSTOMER_DOC])
    generator = FakeGenerator()
    executor = FakeCustomerExecutor()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=executor,
        summariser=FakeSummariser(),
    )

    first_response = orchestrator.process_question("Show customer names starting with ca")
    filtered_response = orchestrator.process_question("which of them have dixon in their names")

    assert first_response["pipeline_stage"] == "sql_executed_successfully"
    assert filtered_response["action_decision"]["action"] == "TRANSFORM_PREVIOUS_RESULT"
    assert filtered_response["pipeline_stage"] == "answered_from_conversation_memory"
    assert filtered_response["retrieval_provider"] == "conversation_memory"
    assert filtered_response["query_results"]["rows"] == [
        {"CUSTOMER_NAME": "Cameron Dixon"},
        {"CUSTOMER_NAME": "Casey Dixon"},
    ]
    assert len(generator.prompts) == 1
    assert len(retriever.questions) == 1
    assert executor.execution_count == 1


def test_orchestrator_blocks_unsafe_mutation_intent_before_retrieval() -> None:
    retriever = FakeRetriever([REVENUE_DOC])
    generator = FakeGenerator()
    orchestrator = QueryOrchestrator(
        retriever=retriever,
        sql_generator=generator,
        sql_executor=FakeExecutor(),
        summariser=FakeSummariser(),
    )

    orchestrator.process_question("What were total sales by product category?")
    response = orchestrator.process_question("Delete all sales rows")

    assert response["pipeline_stage"] == "unsupported_question_no_sql_generated"
    assert response["retrieval_provider"] == "not_run_safety_guard"
    assert "Blocked unsafe intent: delete" in response["support_assessment"]["reason"]
    assert len(generator.prompts) == 1
    assert len(retriever.questions) == 1


def test_orchestrator_skips_sql_generation_for_unsupported_question() -> None:
    orchestrator = QueryOrchestrator(
        retriever=FakeRetriever([]),
        sql_generator=FailingGenerator(),
        sql_executor=SafeSQLExecutor(connection_factory=lambda: None),
        summariser=FakeSummariser(),
    )

    response = orchestrator.process_question("Who won the football match yesterday?")

    assert response["pipeline_stage"] == "unsupported_question_no_sql_generated"
    assert response["generated_sql"]["sql"] is None
    assert response["sql_generation_prompt"] is None
    assert response["query_results"]["status"] == "skipped"
    assert response["answer"]["provider"] == "local_no_answer"
    assert "do not have enough retrieved schema" in response["answer"]["answer"]
