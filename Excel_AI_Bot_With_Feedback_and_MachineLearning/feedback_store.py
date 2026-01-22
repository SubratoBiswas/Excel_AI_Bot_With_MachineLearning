import sqlite3
from typing import Optional, List, Dict, Any


class FeedbackStore:
    def __init__(self, path: str = "feedback.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Better concurrency for Streamlit sessions
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")

        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            catalog_sig TEXT NOT NULL,
            generated_sql TEXT NOT NULL,
            corrected_sql TEXT,
            rating INTEGER, -- 1 good, -1 bad, NULL unknown
            feedback_text TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            feedback_id INTEGER PRIMARY KEY,
            vector BLOB NOT NULL,
            FOREIGN KEY(feedback_id) REFERENCES feedback(id)
        )
        """)

        # Useful indexes
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_catalog ON feedback(catalog_sig);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at);")

        self.conn.commit()

    def add_record(self, question: str, catalog_sig: str, generated_sql: str) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO feedback(question, catalog_sig, generated_sql) VALUES (?,?,?)",
            (question, catalog_sig, generated_sql),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_feedback(
        self,
        record_id: int,
        rating: Optional[int] = None,
        feedback_text: str = "",
        corrected_sql: Optional[str] = None
    ):
        """
        rating: 1 (good), -1 (bad), or None (leave unchanged)
        """
        # Build update dynamically so we don't overwrite rating with None accidentally
        fields = []
        params: List[Any] = []

        if rating is not None:
            fields.append("rating=?")
            params.append(rating)

        fields.append("feedback_text=?")
        params.append(feedback_text)

        fields.append("corrected_sql=?")
        params.append(corrected_sql)

        params.append(record_id)

        sql = f"UPDATE feedback SET {', '.join(fields)} WHERE id=?"
        self.conn.execute(sql, params)
        self.conn.commit()

    def set_embedding(self, record_id: int, vector_bytes: bytes):
        self.conn.execute(
            "INSERT OR REPLACE INTO embeddings(feedback_id, vector) VALUES (?,?)",
            (record_id, vector_bytes),
        )
        self.conn.commit()

    def best_examples(self, catalog_sig: str, limit: int = 20) -> List[Dict]:
        """
        Returns the best training examples for a given schema:
        - rating=1
        - prefer rows with corrected_sql (human fixes)
        - then most recent
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, question, generated_sql, corrected_sql, rating, feedback_text, created_at
            FROM feedback
            WHERE catalog_sig=? AND rating=1
            ORDER BY
                CASE WHEN corrected_sql IS NOT NULL AND TRIM(corrected_sql) <> '' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT ?
            """,
            (catalog_sig, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def top_examples(self, catalog_sig: str, limit: int = 20) -> List[Dict]:
        """
        Backwards compatible alias (if your app still calls top_examples).
        """
        return self.best_examples(catalog_sig, limit=limit)

    def recent_bad_examples(self, catalog_sig: str, limit: int = 10) -> List[Dict]:
        """
        Optional: retrieve recent failures to help the model avoid repeating mistakes.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, question, generated_sql, corrected_sql, rating, feedback_text, created_at
            FROM feedback
            WHERE catalog_sig=? AND rating=-1
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (catalog_sig, limit),
        )
        return [dict(row) for row in cur.fetchall()]
