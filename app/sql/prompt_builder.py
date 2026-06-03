"""Build prompts for SQL generation using retrieved RAG context."""

from __future__ import annotations


class SQLPromptBuilder:
    """Creates a structured prompt package for the SQL generator."""

    def build_prompt(
        self,
        user_question: str,
        retrieved_documents: list[dict],
        conversation_context: str | None = None,
    ) -> str:
        context_block = self._format_documents(retrieved_documents)
        conversation_block = conversation_context or "No prior conversation context."

        return f"""You are an enterprise AI Business Data Analyst Agent.

Your task is to generate safe SQL for a structured business database.
Prepare SQL only. Do not execute SQL.

User question:
{user_question}

Conversation context:
{conversation_block}

Retrieved schema and business context:
{context_block}

Instructions for the SQL generator:
- Generate only safe SELECT SQL.
- Use only tables and columns supported by the retrieved schema context.
- Use retrieved business rules and KPI definitions when they apply.
- For follow-up questions, preserve prior filters, grouping, and scope unless the user changes them.
- Do not modify data.
- Do not generate DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE, or MERGE statements.
- If the user request is ambiguous, ask a clarification question instead of guessing.
- Prefer clear aliases and readable SQL.
- Include a row limit for broad result sets.

Expected output:
- Return only the safe SELECT query when enough context is available.
- If clarification is needed, return a concise clarification question instead of SQL.
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
