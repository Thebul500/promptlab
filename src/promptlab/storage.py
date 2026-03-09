"""SQLite storage layer for templates, runs, and results."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path.home() / ".promptlab" / "promptlab.db"


class Storage:
    """SQLite-backed storage for PromptLab data."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                body TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                UNIQUE(name, version)
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL,
                template_version INTEGER NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                variables TEXT DEFAULT '{}',
                rendered_prompt TEXT NOT NULL,
                response_text TEXT,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                latency_ms REAL DEFAULT 0,
                cost REAL DEFAULT 0,
                error TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES runs(id),
                scorer_type TEXT NOT NULL,
                score REAL NOT NULL,
                details TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                definition TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_templates_name ON templates(name);
            CREATE INDEX IF NOT EXISTS idx_runs_template ON runs(template_name);
            CREATE INDEX IF NOT EXISTS idx_scores_run ON scores(run_id);
        """)
        self.conn.commit()

    # --- Template operations ---

    def save_template(self, name: str, body: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Save a new template version. Auto-increments version."""
        cur = self.conn.execute(
            "SELECT MAX(version) FROM templates WHERE name = ?", (name,)
        )
        row = cur.fetchone()
        version = (row[0] or 0) + 1

        self.conn.execute(
            "INSERT INTO templates (name, version, body, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, version, body, json.dumps(metadata or {}), time.time()),
        )
        self.conn.commit()
        return {"name": name, "version": version, "body": body, "metadata": metadata or {}}

    def get_template(self, name: str, version: int | None = None) -> dict[str, Any] | None:
        """Get a template by name. Returns latest version if version is None."""
        if version is not None:
            cur = self.conn.execute(
                "SELECT * FROM templates WHERE name = ? AND version = ?", (name, version)
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM templates WHERE name = ? ORDER BY version DESC LIMIT 1", (name,)
            )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)

    def list_templates(self) -> list[dict[str, Any]]:
        """List all templates (latest version of each)."""
        cur = self.conn.execute("""
            SELECT t.* FROM templates t
            INNER JOIN (
                SELECT name, MAX(version) as max_ver FROM templates GROUP BY name
            ) latest ON t.name = latest.name AND t.version = latest.max_ver
            ORDER BY t.name
        """)
        return [_row_to_dict(r) for r in cur.fetchall()]

    def list_template_versions(self, name: str) -> list[dict[str, Any]]:
        """List all versions of a template."""
        cur = self.conn.execute(
            "SELECT * FROM templates WHERE name = ? ORDER BY version", (name,)
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def delete_template(self, name: str) -> int:
        """Delete all versions of a template. Returns count deleted."""
        cur = self.conn.execute("DELETE FROM templates WHERE name = ?", (name,))
        self.conn.commit()
        return cur.rowcount

    # --- Run operations ---

    def save_run(
        self,
        template_name: str,
        template_version: int,
        provider: str,
        model: str,
        variables: dict[str, Any],
        rendered_prompt: str,
        response_text: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0,
        cost: float = 0,
        error: str | None = None,
    ) -> int:
        """Save a run result. Returns the run ID."""
        cur = self.conn.execute(
            """INSERT INTO runs (template_name, template_version, provider, model,
               variables, rendered_prompt, response_text, tokens_in, tokens_out,
               latency_ms, cost, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                template_name, template_version, provider, model,
                json.dumps(variables), rendered_prompt, response_text,
                tokens_in, tokens_out, latency_ms, cost, error, time.time(),
            ),
        )
        self.conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("INSERT did not return a row id")
        return cur.lastrowid

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None

    def list_runs(
        self, template_name: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        if template_name:
            cur = self.conn.execute(
                "SELECT * FROM runs WHERE template_name = ? ORDER BY created_at DESC LIMIT ?",
                (template_name, limit),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        return [_row_to_dict(r) for r in cur.fetchall()]

    # --- Score operations ---

    def save_score(self, run_id: int, scorer_type: str, score: float, details: dict[str, Any] | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO scores (run_id, scorer_type, score, details, created_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, scorer_type, score, json.dumps(details or {}), time.time()),
        )
        self.conn.commit()
        if cur.lastrowid is None:
            raise RuntimeError("INSERT did not return a row id")
        return cur.lastrowid

    def get_scores(self, run_id: int) -> list[dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM scores WHERE run_id = ?", (run_id,))
        return [_row_to_dict(r) for r in cur.fetchall()]

    # --- Chain operations ---

    def save_chain(self, name: str, definition: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO chains (name, definition, created_at) VALUES (?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET definition=excluded.definition, created_at=excluded.created_at""",
            (name, json.dumps(definition), time.time()),
        )
        self.conn.commit()

    def get_chain(self, name: str) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM chains WHERE name = ?", (name,))
        row = cur.fetchone()
        return _row_to_dict(row) if row else None

    def list_chains(self) -> list[dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM chains ORDER BY name")
        return [_row_to_dict(r) for r in cur.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a dict, parsing JSON fields."""
    d = dict(row)
    for key in ("metadata", "variables", "details", "definition"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
