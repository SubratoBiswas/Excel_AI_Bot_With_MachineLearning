import io
import re
import json
import hashlib
from typing import Dict, Any

import pandas as pd
import duckdb


def safe_name(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", str(s).strip())
    s = re.sub(r"_{2,}", "_", s).strip("_")
    return s[:80] if s else "table"


class ExcelStore:
    """
    Loads many Excel files and sheets.
    Registers each (file,sheet) as a DuckDB table.
    """

    def __init__(self):
        self.con = duckdb.connect(database=":memory:")
        self.tables: Dict[str, Dict[str, Any]] = {}  # table_name -> metadata

    def add_excel_file(self, file_name: str, file_bytes: bytes):
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        base = safe_name(file_name.rsplit(".", 1)[0])

        for sheet in xls.sheet_names:
            df = xls.parse(sheet_name=sheet)

            # Normalize column names
            df.columns = [safe_name(c) for c in df.columns]

            tname = safe_name(f"{base}__{sheet}")

            # Ensure uniqueness
            original = tname
            i = 2
            while tname in self.tables:
                tname = f"{original}_{i}"
                i += 1

            self.con.register(tname, df)

            self.tables[tname] = {
                "file": file_name,
                "sheet": sheet,
                "rows": int(len(df)),
                "cols": list(df.columns),
                "dtypes": {c: str(df[c].dtype) for c in df.columns},
                "sample": df.head(5).to_dict(orient="records"),
            }

    def catalog(self) -> dict:
        return self.tables

    def catalog_signature(self) -> str:
        """
        Stable signature for the current schema (tables + columns),
        used to scope feedback/training examples to this dataset.
        """
        compact = {t: self.tables[t]["cols"] for t in sorted(self.tables.keys())}
        s = json.dumps(compact, sort_keys=True)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]

    def _validate_sql(self, sql: str) -> str:
        """
        Basic safety checks; llm_agent should already do this too.
        This is defense-in-depth.
        """
        sql = (sql or "").strip().rstrip(";").strip()

        # Disallow any remaining semicolons (prevents multi-statement)
        if ";" in sql:
            raise ValueError("Only one SQL statement is allowed (no semicolons).")

        lowered = sql.lower()
        banned = ["drop ", "delete ", "update ", "insert ", "create ", "alter ", "truncate ", "grant ", "revoke "]
        if any(b in lowered for b in banned):
            raise ValueError("Destructive SQL is not allowed.")

        if not (lowered.startswith("select") or lowered.startswith("with")):
            raise ValueError("SQL must start with SELECT or WITH.")

        return sql

    def run_sql(self, sql: str, limit: int = 200):
        """
        Executes SQL safely by wrapping in a LIMIT.
        """
        sql = self._validate_sql(sql)

        wrapped = f"SELECT * FROM ({sql}) q LIMIT {int(limit)}"
        return self.con.execute(wrapped).fetchdf()
