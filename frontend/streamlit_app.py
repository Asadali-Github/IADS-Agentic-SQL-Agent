"""Streamlit frontend — calls the FastAPI backend.

Owner: Mehdi
Status: placeholder — implement during the hackathon.

UI surfaces (each maps to a backend feature):

  1. Question box + answer panel
       - Direct one-sentence answer from the summariser
       - Result table below it

  2. Confidence indicator
       - Green badge if critic confidence ≥ CONFIDENCE_WARNING_THRESHOLD
       - Yellow warning banner below threshold:
         "I generated this answer, but the schema mapping was ambiguous.
          Please double-check before acting on it."

  3. "How did the AI calculate this?" expander
       - Shows the SQL (syntax-highlighted)
       - Shows the natural-language explanation from the summariser
       - Lists the tables used and why

  4. Friendly error states (never a raw traceback)
       - Out-of-scope: "I understood your question, but our current system
         does not track <X>. Try asking about <Y> instead."
       - Refused: "That question would expose sensitive data I'm not
         allowed to return."
       - Failed after N retries: "I couldn't find a confident answer.
         Here's what I tried, and a suggestion."

  5. Approximate-match notice
       - When row_fallback returned semantically similar rows:
         "No exact match for 'X'. Showing closest results instead."

TODO:
- Implement the four panels above
- API client lives in this file (httpx)
- All copy strings centralised at the top of the module for easy editing
- Write tests in tests/unit/test_streamlit_app.py
"""
