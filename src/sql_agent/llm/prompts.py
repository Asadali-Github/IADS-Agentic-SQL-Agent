"""Prompt loader - reads markdown templates from prompts/ and fills placeholders.

Owner: Asad.

Templates live in the top-level prompts/ directory as markdown so they are easy
to diff and iterate on (see notebooks/03_prompt_iteration.ipynb). Placeholders
use ${name} / $name syntax (string.Template), filled via render().

    from sql_agent.llm.prompts import render
    text = render("sql_explanation", question=q, sql=sql, schema_summary=s)

Unknown placeholders are left intact (safe_substitute) so a half-filled template
never raises mid-demo.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


@lru_cache(maxsize=None)
def load_template(name: str) -> str:
    """Read prompts/<name>.md (cached). `name` is given without extension."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render(name: str, **kwargs: object) -> str:
    """Load prompts/<name>.md and substitute ${placeholders} from kwargs."""
    template = Template(load_template(name))
    return template.safe_substitute(**{k: str(v) for k, v in kwargs.items()})


def clear_cache() -> None:
    """Drop the template cache (call after editing a prompt during iteration)."""
    load_template.cache_clear()
