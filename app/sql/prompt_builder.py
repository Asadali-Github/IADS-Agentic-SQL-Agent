"""Build prompts for future SQL generation using retrieved RAG context."""

from __future__ import annotations


class SQLPromptBuilder:
    """Creates a structured prompt package for a future SQL generator."""

    def build_prompt(self, user_question: str, retrieved_documents: list[dict]) -> str:
        context_block = self._format_documents(retrieved_documents)

        return f"""You are an enterprise AI Business Data Analyst Agent.

Your future task is to generate safe SQL for a structured business database.
For this prototype step, prepare SQL only as a future action. Do not execute SQL.

User question:
{user_question}

Retrieved schema and business context:
{context_block}

Instructions for the future SQL generator:
- Generate only safe SELECT SQL.
- Use only tables and columns supported by the retrieved schema context.
- Use retrieved business rules and KPI definitions when they apply.
- Do not modify data.
- Do not generate DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE, or MERGE statements.
- If the user request is ambiguous, ask a clarification question instead of guessing.
- Prefer clear aliases and readable SQL.
- Include a row limit for broad result sets.

Expected future output format:
- sql: the safe SELECT query, or null if clarification is needed
- clarification_question: a concise question if the request is ambiguous
- reasoning: short explanation of which retrieved documents were used
"""

    def _format_documents(self, documents: list[dict]) -> str:
        if not documents:
            return "No relevant documents were retrieved."

        formatted_documents = []
        for index, document in enumerate(documents, start=1):
            formatted_documents.append(
                "\n".join(
                    [
                        f"{index}. [{document['type']}] {document['title']}",
                        f"   id: {document['id']}",
                        f"   content: {document['content']}",
                    ]
                )
            )

        return "\n\n".join(formatted_documents)
