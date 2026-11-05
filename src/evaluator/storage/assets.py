"""Versioned asset inputs with provenance and an append-only change history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from evaluator.storage.database import connection
from evaluator.template_engine.engine import InputValue


class AssetStore:
    def __init__(self, database: str | Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with connection(self.database) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    created_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS asset_inputs (
                    asset_id TEXT NOT NULL,
                    input_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_detail_json TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_utc TEXT NOT NULL,
                    PRIMARY KEY(asset_id, input_key),
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id)
                );
                CREATE TABLE IF NOT EXISTS asset_input_changes (
                    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL,
                    input_key TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    changed_utc TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    old_value_json TEXT,
                    new_value_json TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_detail_json TEXT NOT NULL
                );
                """
            )

    def create_asset(self, asset_id: str, label: str, *, who: str) -> None:
        asset_id, label, who = asset_id.strip(), label.strip(), who.strip()
        if not asset_id or not label or not who:
            raise ValueError("Asset ID, label, and creator are required")
        with connection(self.database) as db:
            db.execute(
                "INSERT INTO assets VALUES (?, ?, ?, ?)",
                (asset_id, label, datetime.now(timezone.utc).isoformat(), who),
            )

    def set_input(
        self,
        asset_id: str,
        key: str,
        value: Any,
        unit: str,
        *,
        who: str,
        why: str,
        source_type: str = "manual",
        source_detail: Mapping[str, Any] | None = None,
    ) -> int:
        """Create a new input version and require who/when/why/source provenance."""
        key, unit, who, why = key.strip(), unit.strip(), who.strip(), why.strip()
        if not key or not unit or not who or not why:
            raise ValueError("Input key, unit, author, and change reason are required")
        if source_type not in {"manual", "sheet", "code_table"}:
            raise ValueError(f"Unsupported provenance type {source_type!r}")
        detail = dict(source_detail or {})
        if source_type == "manual" and not detail.get("entered_by"):
            detail["entered_by"] = who
        if source_type == "code_table":
            if not detail.get("verification") or not detail.get("source_sha256"):
                raise ValueError("Code-table inputs require verification status and a source SHA-256")
        value_json = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
        detail_json = json.dumps(detail, ensure_ascii=False, default=str, sort_keys=True)
        now = datetime.now(timezone.utc).isoformat()
        with connection(self.database) as db:
            if not db.execute("SELECT 1 FROM assets WHERE asset_id=?", (asset_id,)).fetchone():
                raise KeyError(f"Unknown asset {asset_id!r}")
            old = db.execute(
                "SELECT value_json, version FROM asset_inputs WHERE asset_id=? AND input_key=?",
                (asset_id, key),
            ).fetchone()
            version = int(old["version"]) + 1 if old else 1
            old_value = old["value_json"] if old else None
            db.execute(
                """INSERT INTO asset_inputs VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(asset_id, input_key) DO UPDATE SET
                     value_json=excluded.value_json, unit=excluded.unit,
                     source_type=excluded.source_type, source_detail_json=excluded.source_detail_json,
                     version=excluded.version, updated_utc=excluded.updated_utc""",
                (asset_id, key, value_json, unit, source_type, detail_json, version, now),
            )
            db.execute(
                "INSERT INTO asset_input_changes(asset_id,input_key,version,changed_utc,changed_by,reason,old_value_json,new_value_json,source_type,source_detail_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (asset_id, key, version, now, who, why, old_value, value_json, source_type, detail_json),
            )
        return version

    def inputs(self, asset_id: str) -> dict[str, InputValue]:
        with connection(self.database) as db:
            rows = db.execute(
                "SELECT input_key,value_json,unit,source_type,source_detail_json FROM asset_inputs WHERE asset_id=?",
                (asset_id,),
            ).fetchall()
        return {
            row["input_key"]: InputValue(
                value=json.loads(row["value_json"]),
                unit=row["unit"],
                provenance={"source_type": row["source_type"], **json.loads(row["source_detail_json"])},
            )
            for row in rows
        }

    def history(self, asset_id: str, key: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM asset_input_changes WHERE asset_id=?"
        parameters: tuple[Any, ...] = (asset_id,)
        if key is not None:
            query += " AND input_key=?"
            parameters += (key,)
        query += " ORDER BY change_id"
        with connection(self.database) as db:
            rows = db.execute(query, parameters).fetchall()
        return [
            {**dict(row), "old_value": json.loads(row["old_value_json"]) if row["old_value_json"] else None,
             "new_value": json.loads(row["new_value_json"]),
             "source_detail": json.loads(row["source_detail_json"])}
            for row in rows
        ]

    def assets(self) -> list[dict[str, str]]:
        with connection(self.database) as db:
            return [dict(row) for row in db.execute("SELECT * FROM assets ORDER BY asset_id")]
