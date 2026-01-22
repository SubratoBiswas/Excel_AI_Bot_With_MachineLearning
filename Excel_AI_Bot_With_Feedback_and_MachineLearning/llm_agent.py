import json
from typing import Any, Dict, List, Optional

from openai import OpenAI

client = OpenAI()

SYSTEM_PROMPT = """You are an Excel analytics assistant.
You will be given:
- TRAINING_EXAMPLES from prior user feedback (optional)
- A catalog of SQL tables (DuckDB) derived from uploaded Excel files.

Your job: produce ONE DuckDB-compatible SQL query that answers the question.

Rules:
- Only use tables/columns from the catalog.
- Follow TRAINING_EXAMPLES conventions (joins, filters, definitions) unless they conflict with the current schema.
- Prefer joins on clearly matching keys (e.g., CustomerID, Date, Region) when asked to compare across tables.
- If the question is ambiguous, make a reasonable assumption and state it in the explanation.
- Never write destructive SQL (no DROP/UPDATE/DELETE/INSERT/CREATE/ALTER).
- Return JSON matching the schema.
- Do NOT include a trailing semicolon in SQL.
- Return only ONE statement: a SELECT or a WITH ... SELECT query.
"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string"},
        "explanation": {"type": "string"}
    },
    "required": ["sql", "explanation"],
    "additionalProperties": False
}


def _compact_catalog(catalog: Dict[str, Any], max_tables: int = 80) -> Dict[str, Any]:
    """
    Keep catalog small to avoid huge prompts.
    Includes table -> file/sheet/rows/cols/dtypes + tiny sample.
    """
    out = {}
    for i, (t, m) in enumerate(catalog.items()):
        if i >= max_tables:
            break
        out[t] = {
            "file": m.get("file"),
            "sheet": m.get("sheet"),
            "rows": m.get("rows"),
            "cols": m.get("cols"),
            "dtypes": m.get("dtypes"),
            "sample": (m.get("sample") or [])[:3],
        }
    return out


def _compact_examples(examples: Optional[List[Dict[str, Any]]], max_examples: int = 5) -> List[Dict[str, str]]:
    """
    Convert feedback rows to a short few-shot list.
    Prefer corrected_sql when present.
    """
    if not examples:
        return []

    few_shots: List[Dict[str, str]] = []
    for ex in examples[:max_examples]:
        q = (ex.get("question") or "").strip()
        sql = (ex.get("corrected_sql") or ex.get("generated_sql") or "").strip()
        if q and sql:
            few_shots.append({"q": q, "sql": sql})
    return few_shots


def _sanitize_sql(sql: str) -> str:
    """
    Minimal safety:
    - strip trailing semicolons
    - block multi-statement by disallowing ';' anywhere
    - block destructive keywords
    - enforce query starts with SELECT/WITH
    """
    sql = (sql or "").strip().rstrip(";").strip()

    if ";" in sql:
        raise ValueError("SQL contains a semicolon; only one statement is allowed.")

    lowered = sql.lower()
    banned = ["drop ", "delete ", "update ", "insert ", "create ", "alter ", "truncate ", "grant ", "revoke "]
    if any(b in lowered for b in banned):
        raise ValueError("Destructive SQL is not allowed.")

    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("SQL must start with SELECT or WITH.")

    return sql


def generate_sql(question: str, catalog: dict, examples: Optional[list] = None) -> dict:
    catalog_compact = _compact_catalog(catalog)
    few_shots = _compact_examples(examples, max_examples=5)

    resp = client.responses.create(
        model="gpt-5.2",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"TRAINING_EXAMPLES:\n{json.dumps(few_shots, ensure_ascii=False)}"},
            {"role": "user", "content": f"CATALOG:\n{json.dumps(catalog_compact, ensure_ascii=False)[:120000]}"},
            {"role": "user", "content": f"QUESTION:\n{question}"}
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "sql_plan",
                "schema": OUTPUT_SCHEMA,
                "strict": True
            }
        }
    )

    plan = json.loads(resp.output_text)

    # Sanitize SQL before returning (prevents your earlier ";" crash)
    plan["sql"] = _sanitize_sql(plan.get("sql", ""))
    plan["explanation"] = (plan.get("explanation") or "").strip()

    return plan
