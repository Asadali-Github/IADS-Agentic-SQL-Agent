"""Small in-process conversation memory for follow-up business questions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

FOLLOW_UP_MARKERS = {
    "also",
    "again",
    "same",
    "previous",
    "last",
    "instead",
    "compare",
    "it",
    "this",
    "that",
    "them",
    "these",
    "those",
}

FOLLOW_UP_PHRASES = (
    "what about",
    "how about",
    "and ",
    "for ",
    "same for",
    "do the same",
)

BUSINESS_FOLLOW_UP_TERMS = {
    "category",
    "city",
    "country",
    "customer",
    "customers",
    "margin",
    "month",
    "monthly",
    "orders",
    "product",
    "products",
    "profit",
    "quantity",
    "region",
    "revenue",
    "sales",
    "state",
    "year",
}

RESULT_REFERENCE_WORDS = {
    "above",
    "answer",
    "list",
    "previous",
    "result",
    "results",
    "row",
    "rows",
    "table",
    "this",
    "them",
    "these",
    "those",
}

ENTITY_REFERENCE_COLUMNS = {
    "product": ("PRODUCT_NAME", "PRODUCT", "PRODUCT_ID"),
    "customer": ("CUSTOMER_NAME", "CUSTOMER", "CUSTOMER_ID"),
    "region": ("REGION",),
    "category": ("CATEGORY", "SUB_CATEGORY"),
    "city": ("CITY",),
    "state": ("STATE",),
    "country": ("COUNTRY",),
    "segment": ("SEGMENT", "CUSTOMER_SEGMENT"),
    "order": ("ORDER_ID", "ORDER"),
}

LOWEST_MARKERS = {"bottom", "least", "lowest", "min", "minimum", "smallest", "worst"}
HIGHEST_MARKERS = {"best", "highest", "largest", "max", "maximum", "most", "top"}
FIRST_MARKERS = {"first", "1st"}
LAST_MARKERS = {"last", "final"}
SORT_MARKERS = {"order", "ordered", "reorder", "sort", "sorted"}
ASCENDING_MARKERS = {"asc", "ascending", "ascendingly", "increasing"}
DESCENDING_MARKERS = {"desc", "descending", "descendingly", "decreasing"}

METRIC_ALIASES = {
    "profit": ("sales", "revenue", "quantity", "orders"),
    "revenue": ("profit", "sales", "quantity", "orders"),
    "sales": ("profit", "revenue", "quantity", "orders"),
    "quantity": ("profit", "revenue", "sales", "orders"),
    "orders": ("profit", "revenue", "sales", "quantity"),
}


@dataclass(frozen=True)
class QuestionResolution:
    """How the current user question should be used by the pipeline."""

    original_question: str
    resolved_question: str
    retrieval_question: str
    is_follow_up: bool
    conversation_context: str | None = None

    @property
    def support_question(self) -> str:
        """Question text used for term-based support checks."""
        return self.retrieval_question


@dataclass(frozen=True)
class MemoryAnswer:
    """Answer derived directly from prior result rows."""

    answer: str
    rows: list[dict[str, Any]]
    columns: list[str]
    source_turn: ConversationTurn


@dataclass(frozen=True)
class ConversationTurn:
    """One completed user question and pipeline response."""

    original_question: str
    resolved_question: str
    answer: dict[str, Any]
    generated_sql: dict[str, Any]
    query_results: dict[str, Any]
    retrieved_documents: list[dict[str, Any]]
    pipeline_stage: str

    @property
    def is_successful(self) -> bool:
        """Return true when the turn produced usable SQL-backed information."""
        return self.pipeline_stage in {
            "sql_executed_successfully",
            "sql_executed_with_fallback",
        } and bool(self.generated_sql.get("sql"))

    @property
    def has_result_rows(self) -> bool:
        """Return true when this turn displayed rows the user can refer to."""
        return bool(self.query_results.get("rows"))


class ConversationMemory:
    """Remember recent successful turns so short follow-ups can be grounded."""

    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self.turns: list[ConversationTurn] = []

    def resolve(self, user_question: str) -> QuestionResolution:
        """Expand a follow-up question with the latest successful business context."""
        question = user_question.strip()
        previous_turn = self.latest_successful_turn()
        if (
            not previous_turn
            or not self._looks_like_follow_up(question)
            or (
                not self._starts_with_strong_follow_up(question)
                and self._is_self_contained_business_question(question)
            )
        ):
            return QuestionResolution(
                original_question=question,
                resolved_question=question,
                retrieval_question=question,
                is_follow_up=False,
            )

        resolved_question = self._standalone_follow_up(question, previous_turn)
        conversation_context = (
            f"Previous successful question: {previous_turn.original_question}\n"
            f"Previous SQL: {previous_turn.generated_sql.get('sql')}\n"
            "Use the previous filters, grouping, and business scope unless the follow-up "
            "explicitly changes them."
        )
        return QuestionResolution(
            original_question=question,
            resolved_question=resolved_question,
            retrieval_question=f"{previous_turn.original_question} {question}",
            is_follow_up=True,
            conversation_context=conversation_context,
        )

    def resolve_question(self, user_question: str) -> str:
        """Compatibility wrapper returning only the prompt-facing question."""
        return self.resolve(user_question).resolved_question

    def record(self, response: dict[str, Any]) -> None:
        """Store a completed pipeline response."""
        self.turns.append(
            ConversationTurn(
                original_question=response["original_question"],
                resolved_question=response.get("resolved_question", response["original_question"]),
                answer=response.get("answer", {}),
                generated_sql=response.get("generated_sql", {}),
                query_results=response.get("query_results", {}),
                retrieved_documents=response.get("retrieved_documents", []),
                pipeline_stage=response.get("pipeline_stage", ""),
            )
        )
        self.turns = self.turns[-self.max_turns :]

    def latest_successful_turn(self) -> ConversationTurn | None:
        """Return the latest turn that produced usable data."""
        for turn in reversed(self.turns):
            if turn.is_successful:
                return turn
        return None

    def latest_result_turn(self) -> ConversationTurn | None:
        """Return the latest turn that displayed tabular data."""
        for turn in reversed(self.turns):
            if turn.has_result_rows:
                return turn
        return None

    def answer_from_previous_results(self, user_question: str) -> MemoryAnswer | None:
        """Answer simple table-reference follow-ups without generating new SQL."""
        question = user_question.strip()
        previous_turn = self.latest_result_turn()
        if not previous_turn or not self._looks_like_result_reference(question):
            return None

        rows = list(previous_turn.query_results.get("rows") or [])
        if not rows:
            return None

        sorted_rows = self._sort_referenced_rows(question, rows)
        if sorted_rows:
            metric_column = self._metric_column(question, sorted_rows)
            direction = self._sort_direction(question)
            metric_name = (
                self._humanize_label(metric_column) if metric_column else "the displayed rows"
            )
            return MemoryAnswer(
                answer=(
                    f"Here is the previous result sorted {direction} by {metric_name}."
                ),
                rows=sorted_rows,
                columns=list(sorted_rows[0].keys()),
                source_turn=previous_turn,
            )

        selected_row = self._select_referenced_row(question, rows)
        if not selected_row:
            return None

        metric_column = self._metric_column(question, rows)
        answer = self._build_result_reference_answer(question, selected_row, metric_column)
        return MemoryAnswer(
            answer=answer,
            rows=[selected_row],
            columns=list(selected_row.keys()),
            source_turn=previous_turn,
        )

    def resolve_displayed_entity_reference(self, user_question: str) -> QuestionResolution | None:
        """Bind phrases like "this product" to the latest displayed single row."""
        question = user_question.strip()
        match = re.search(
            r"\b(?P<phrase>(?:this|that|selected|same)\s+"
            r"(?P<entity>product|customer|region|category|city|state|country|segment|order))\b",
            question,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        latest_result = self.latest_result_turn()
        if not latest_result:
            return None

        rows = list(latest_result.query_results.get("rows") or [])
        if len(rows) != 1:
            return None

        row = rows[0]
        entity = match.group("entity").lower()
        column = self._entity_column(entity, row)
        if not column:
            return None

        value = row.get(column)
        if value in (None, ""):
            return None

        previous_successful = self.latest_successful_turn()
        phrase = match.group("phrase")
        display_row = "\n".join(
            f"{column_name}: {self._format_value(column_value)}"
            for column_name, column_value in row.items()
        )
        previous_context = ""
        retrieval_parts = [question, column, str(value)]
        if previous_successful:
            previous_context = (
                f"Previous successful question: {previous_successful.original_question}\n"
                f"Previous SQL: {previous_successful.generated_sql.get('sql')}\n"
            )
            retrieval_parts.insert(0, previous_successful.original_question)

        conversation_context = (
            f"{previous_context}"
            f"Latest displayed result row:\n{display_row}\n"
            "Resolved entity reference:\n"
            f'The phrase "{phrase}" means {column} = {value!r}.\n'
            "Preserve this entity filter in the generated SQL."
        )
        return QuestionResolution(
            original_question=question,
            resolved_question=f"{question} ({phrase} means {column} = {value!r})",
            retrieval_question=" ".join(retrieval_parts),
            is_follow_up=True,
            conversation_context=conversation_context,
        )

    def _looks_like_follow_up(self, question: str) -> bool:
        normalized_question = question.lower().strip()
        words = normalized_question.split()
        if self._starts_with_strong_follow_up(question):
            return True

        if any(marker in words for marker in FOLLOW_UP_MARKERS):
            return True

        return len(words) <= 4 and any(word in BUSINESS_FOLLOW_UP_TERMS for word in words)

    def _starts_with_strong_follow_up(self, question: str) -> bool:
        normalized_question = question.lower().strip()
        return any(normalized_question.startswith(phrase) for phrase in FOLLOW_UP_PHRASES)

    def _is_self_contained_business_question(self, question: str) -> bool:
        words = set(re.findall(r"[a-zA-Z0-9_]+", question.lower()))
        business_terms = words.intersection(BUSINESS_FOLLOW_UP_TERMS)
        has_analysis_shape = bool(
            words.intersection({"bottom", "least", "top"})
            or words.intersection({"by", "group", "grouped", "monthly"})
        )
        return len(business_terms) >= 2 and has_analysis_shape

    def _looks_like_result_reference(self, question: str) -> bool:
        normalized_question = question.lower().strip()
        words = set(re.findall(r"[a-zA-Z0-9_]+", normalized_question))
        has_reference = bool(words.intersection(RESULT_REFERENCE_WORDS))
        has_sort = bool(words.intersection(SORT_MARKERS))
        has_sort_direction = bool(words.intersection(ASCENDING_MARKERS | DESCENDING_MARKERS))
        has_selector = bool(
            words.intersection(
                LOWEST_MARKERS | HIGHEST_MARKERS | FIRST_MARKERS | LAST_MARKERS
            )
        )
        if has_sort and (has_reference or has_sort_direction):
            return True
        return has_selector and (has_reference or len(words) <= 4)

    def _entity_column(self, entity: str, row: dict[str, Any]) -> str | None:
        columns = list(row.keys())
        upper_to_original = {column.upper(): column for column in columns}
        for candidate in ENTITY_REFERENCE_COLUMNS.get(entity, ()):
            if candidate in upper_to_original:
                return upper_to_original[candidate]

        entity_token = entity.upper()
        for column in columns:
            if entity_token in column.upper():
                return column
        return None

    def _sort_referenced_rows(
        self,
        question: str,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        words = set(re.findall(r"[a-zA-Z0-9_]+", question.lower()))
        if not words.intersection(SORT_MARKERS):
            return None

        metric_column = self._metric_column(question, rows)
        if metric_column:
            reverse = self._sort_direction(question) == "descending"
            return sorted(
                rows,
                key=lambda row: self._numeric_value(row.get(metric_column)),
                reverse=reverse,
            )

        reverse = self._sort_direction(question) == "descending"
        return sorted(rows, key=lambda row: str(tuple(row.values())).lower(), reverse=reverse)

    def _sort_direction(self, question: str) -> str:
        words = set(re.findall(r"[a-zA-Z0-9_]+", question.lower()))
        if words.intersection(DESCENDING_MARKERS):
            return "descending"
        return "ascending"

    def _select_referenced_row(
        self,
        question: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        words = set(re.findall(r"[a-zA-Z0-9_]+", question.lower()))
        metric_column = self._metric_column(question, rows)

        if words.intersection(FIRST_MARKERS | HIGHEST_MARKERS) and metric_column:
            return max(rows, key=lambda row: self._numeric_value(row.get(metric_column)))

        if words.intersection(LAST_MARKERS) and not metric_column:
            return rows[-1]

        if words.intersection(LAST_MARKERS | LOWEST_MARKERS) and metric_column:
            return min(rows, key=lambda row: self._numeric_value(row.get(metric_column)))

        if words.intersection(FIRST_MARKERS):
            return rows[0]

        return None

    def _metric_column(self, question: str, rows: list[dict[str, Any]]) -> str | None:
        numeric_columns = self._numeric_columns(rows)
        if not numeric_columns:
            return None

        question_terms = set(re.findall(r"[a-zA-Z0-9_]+", question.lower()))
        for column in numeric_columns:
            column_terms = set(re.findall(r"[a-zA-Z0-9_]+", column.lower()))
            if question_terms.intersection(column_terms):
                return column

        return numeric_columns[-1]

    def _numeric_columns(self, rows: list[dict[str, Any]]) -> list[str]:
        columns = list(rows[0].keys())
        numeric_columns = []
        for column in columns:
            values = [row.get(column) for row in rows if row.get(column) is not None]
            if values and all(self._is_numeric(value) for value in values):
                numeric_columns.append(column)
        return numeric_columns

    def _is_numeric(self, value: Any) -> bool:
        if isinstance(value, bool) or value is None:
            return False
        if isinstance(value, int | float):
            return True
        try:
            float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return False
        return True

    def _numeric_value(self, value: Any) -> float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        return float(str(value).replace(",", ""))

    def _build_result_reference_answer(
        self,
        question: str,
        selected_row: dict[str, Any],
        metric_column: str | None,
    ) -> str:
        words = set(re.findall(r"[a-zA-Z0-9_]+", question.lower()))
        direction = "selected"
        if words.intersection(LOWEST_MARKERS | LAST_MARKERS):
            direction = "lowest"
        if words.intersection(HIGHEST_MARKERS | FIRST_MARKERS):
            direction = "highest"

        label = self._row_label(selected_row, metric_column)
        if metric_column:
            value = self._format_value(selected_row[metric_column])
            metric_name = self._humanize_label(metric_column)
            return (
                f"Among the previous results, {label} has the {direction} "
                f"{metric_name}: {value}."
            )

        return f"Among the previous results, the {direction} row is {label}."

    def _row_label(self, row: dict[str, Any], metric_column: str | None) -> str:
        label_values = [
            str(value)
            for column, value in row.items()
            if column != metric_column and not self._is_numeric(value)
        ]
        if label_values:
            return " / ".join(label_values)
        return ", ".join(
            f"{self._humanize_label(column)}: {self._format_value(value)}"
            for column, value in row.items()
            if column != metric_column
        )

    def _humanize_label(self, label: str) -> str:
        return label.replace("_", " ").strip().lower()

    def _format_value(self, value: Any) -> str:
        if isinstance(value, float):
            return f"{value:,.2f}"
        if isinstance(value, int) and not isinstance(value, bool):
            return f"{value:,}"
        return str(value)

    def _standalone_follow_up(
        self,
        question: str,
        previous_turn: ConversationTurn,
    ) -> str:
        previous_question = previous_turn.original_question.strip()
        metric = self._mentioned_metric(question)
        if metric:
            replaced = self._replace_previous_metric(previous_question, metric)
            if replaced != previous_question:
                return replaced

        return (
            f"{question.strip()} "
            f"(same business context as previous question: {previous_question})"
        )

    def _mentioned_metric(self, question: str) -> str | None:
        words = set(re.findall(r"[a-zA-Z0-9_]+", question.lower()))
        for metric in METRIC_ALIASES:
            if metric in words:
                return metric
        return None

    def _replace_previous_metric(self, previous_question: str, new_metric: str) -> str:
        margin_rewrite = self._replace_profit_margin_metric(previous_question, new_metric)
        if margin_rewrite:
            return margin_rewrite

        aliases = METRIC_ALIASES[new_metric]
        replacements = [
            (rf"\btotal\s+{old_metric}\b", f"total {new_metric}")
            for old_metric in aliases
        ]
        replacements.extend((rf"\b{old_metric}\b", new_metric) for old_metric in aliases)

        for pattern, replacement in replacements:
            updated_question = re.sub(
                pattern,
                replacement,
                previous_question,
                count=1,
                flags=re.IGNORECASE,
            )
            if updated_question != previous_question:
                return updated_question
        return previous_question

    def _replace_profit_margin_metric(
        self,
        previous_question: str,
        new_metric: str,
    ) -> str | None:
        if "profit margin" not in previous_question.lower():
            return None

        grouping = self._extract_grouping(previous_question)
        if not grouping:
            return None

        metric_label = "sales" if new_metric == "sales" else new_metric
        return f"What is total {metric_label} by {grouping}?"

    def _extract_grouping(self, question: str) -> str | None:
        normalized_question = question.lower()
        for grouping in (
            "category",
            "city",
            "country",
            "customer",
            "month",
            "product",
            "region",
            "state",
            "year",
        ):
            if re.search(rf"\bby\s+{grouping}\b", normalized_question):
                return grouping
        return None
