"""Readings-only intake, row-pair evaluation, and copy-only workbook export."""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import date, datetime, timezone
from xml.etree import ElementTree as ET
from pathlib import Path
from typing import Any
from uuid import uuid4

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from evaluator.importing.detect import extract
from evaluator.importing.layout_profiles import BUILTIN_LAYOUTS, preview_layout, validate_custom_profile
from evaluator.storage.database import connection
from evaluator.template_engine.row_calculations import evaluate_reading_pair, load_calculation_profiles


class ReadingsOnlyService:
    def __init__(self, service):
        self.service = service
        self.database = service.repository.path
        self.profile_file = service.project_dir / "layout_profiles.json"
        with connection(self.database) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS readings_only_pairs (
                    pair_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, sheet_name TEXT NOT NULL,
                    profile_id TEXT NOT NULL, asset_id TEXT NOT NULL, location TEXT NOT NULL,
                    pair_json TEXT NOT NULL, imported_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS readings_only_results (
                    result_id TEXT PRIMARY KEY, pair_id TEXT NOT NULL, profile_id TEXT NOT NULL,
                    result_json TEXT NOT NULL, evaluated_utc TEXT NOT NULL
                );
            """)

    def profiles(self) -> dict[str, dict[str, Any]]:
        profiles = dict(BUILTIN_LAYOUTS)
        if self.profile_file.exists():
            data = json.loads(self.profile_file.read_text(encoding="utf-8"))
            if data.get("schema_version") != "1.0":
                raise ValueError("Invalid saved layout profile file")
            profiles.update({p["id"]: p for p in data.get("profiles", [])})
        return profiles

    def preview(self, source_id: str, sheet: str) -> dict[str, Any]:
        source = self._source(source_id)
        return preview_layout(source.stored_path, sheet)

    def save_custom_profile(self, profile: dict[str, Any], *, who: str, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise ValueError("The column mapping must be explicitly confirmed")
        who = who.strip()
        if not who:
            raise ValueError("Profile confirmer is required")
        saved = validate_custom_profile(profile)
        saved["confirmed_by"] = who
        data = {"schema_version": "1.0", "profiles": []}
        if self.profile_file.exists():
            data = json.loads(self.profile_file.read_text(encoding="utf-8"))
        existing = [p for p in data.get("profiles", []) if p["id"] != saved["id"]]
        existing.append(saved)
        data["profiles"] = existing
        self.profile_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return saved

    def import_sheet(self, source_id: str, sheet: str, profile_id: str, asset_id: str) -> dict[str, Any]:
        source = self._source(source_id)
        if not any(a["asset_id"] == asset_id for a in self.service.assets.assets()):
            raise KeyError(f"Unknown asset {asset_id!r}")
        profile = self.profiles().get(profile_id)
        if not profile:
            raise KeyError(f"Unknown layout profile {profile_id!r}")
        if profile["kind"] == "custom":
            pairs = self._custom_pairs(source.stored_path, source_id, sheet, profile)
        else:
            pairs = self._builtin_pairs(source.stored_path, source_id, sheet, profile)
        now = datetime.now(timezone.utc).isoformat()
        with connection(self.database) as db:
            for pair in pairs:
                db.execute("INSERT INTO readings_only_pairs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (uuid4().hex, source_id, sheet, profile_id, asset_id, pair["location"], json.dumps(pair, default=str), now))
        return {"source_id": source_id, "sheet": sheet, "profile_id": profile_id, "asset_id": asset_id,
                "imported_pairs": len(pairs), "unresolved": sum(not p.get("previous_date") or not p.get("current_date") for p in pairs)}

    def pairs(self, source_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM readings_only_pairs"
        args: tuple[Any, ...] = ()
        if source_id:
            query += " WHERE source_id=?"; args = (source_id,)
        query += " ORDER BY imported_utc, pair_id"
        with connection(self.database) as db:
            rows = db.execute(query, args).fetchall()
        return [{**dict(r), "pair": json.loads(r["pair_json"])} for r in rows]

    def evaluate(self, pair_id: str, calculation_profile_id: str) -> dict[str, Any]:
        with connection(self.database) as db:
            row = db.execute("SELECT * FROM readings_only_pairs WHERE pair_id=?", (pair_id,)).fetchone()
        if not row:
            raise KeyError(f"Unknown reading pair {pair_id!r}")
        pair = json.loads(row["pair_json"])
        if not pair.get("previous_date") or not pair.get("current_date"):
            return {"pair_id": pair_id, "status": "missing_inputs", "missing_inputs": ["previous_date or current_date is missing or conflicting"], "outputs": [], "trace": []}
        result = evaluate_reading_pair(calculation_profile_id, pair, self.service.assets.inputs(row["asset_id"]))
        result["pair_id"] = pair_id
        result["asset_id"] = row["asset_id"]
        result["status_label"] = "DRAFT / NOT VALIDATED"
        with connection(self.database) as db:
            db.execute("INSERT INTO readings_only_results VALUES (?, ?, ?, ?, ?)",
                       (uuid4().hex, pair_id, calculation_profile_id, json.dumps(result, default=str), datetime.now(timezone.utc).isoformat()))
        return result

    def results(self) -> list[dict[str, Any]]:
        with connection(self.database) as db:
            rows = db.execute("""SELECT r.result_id,r.pair_id,r.profile_id,r.result_json,p.source_id,p.sheet_name,p.location
                                FROM readings_only_results r JOIN readings_only_pairs p USING(pair_id)
                                ORDER BY r.evaluated_utc""").fetchall()
        return [{**dict(r), "result": json.loads(r["result_json"])} for r in rows]

    def export_copy(self, source_id: str, *, result_ids: list[str] | None = None) -> Path:
        source = self._source(source_id)
        selected = set(result_ids or ())
        rows = self.results()
        rows = [r for r in rows if r["source_id"] == source_id and (not selected or r["result_id"] in selected)]
        if not rows:
            raise ValueError("Evaluate at least one imported row before exporting")
        target_dir = self.service.project_dir / "exports"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{source.stored_path.stem}-evaluated-{uuid4().hex[:8]}{source.stored_path.suffix}"
        shutil.copy2(source.stored_path, target)
        results = [["DRAFT / NOT VALIDATED"], ["Location", "Profile", "Status", "Output", "Value", "Unit", "Source sheet"]]
        ledger = [["Pair ID", "Profile", "Location", "Status", "Node", "Expression", "Input provenance", "Value"]]
        for row in rows:
            result = row["result"]
            for output in result.get("outputs", []):
                results.append([row["location"], result.get("profile_label", row["profile_id"]), result["status"], output.get("label"), str(output.get("value")), output.get("unit"), row["sheet_name"]])
            for trace in result.get("trace", []):
                ledger.append([row["pair_id"], row["profile_id"], row["location"], result["status"], trace["node_id"], trace["expression"], json.dumps(trace["inputs"], default=str), str(trace["value"])])
            if result.get("status") != "evaluated":
                ledger.append([row["pair_id"], row["profile_id"], row["location"], result["status"], "MISSING", "", json.dumps(result.get("missing_inputs", [])), ""])
        self._append_result_sheets(target, [("Results", results), ("Calculation Ledger", ledger)])
        return target

    @staticmethod
    def _append_result_sheets(path: Path, sheets: list[tuple[str, list[list[Any]]]]) -> None:
        """Add plain-value sheets at the OOXML package level, preserving original parts."""
        ns_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ns_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        ns_pkg_rel = "http://schemas.openxmlformats.org/package/2006/relationships"
        ns_ct = "http://schemas.openxmlformats.org/package/2006/content-types"
        ET.register_namespace("", ns_main)
        ET.register_namespace("r", ns_rel)
        temp = path.with_suffix(path.suffix + ".tmp")
        with zipfile.ZipFile(path, "r") as zin:
            files = {item.filename: (item, zin.read(item.filename)) for item in zin.infolist()}
        workbook = ET.fromstring(files["xl/workbook.xml"][1])
        relationships = ET.fromstring(files["xl/_rels/workbook.xml.rels"][1])
        content_types = ET.fromstring(files["[Content_Types].xml"][1])
        sheet_parent = workbook.find(f"{{{ns_main}}}sheets")
        if sheet_parent is None: raise ValueError("Workbook package has no sheet collection")
        existing = {item.get("name") for item in sheet_parent}
        rel_ids = [int(m.group(1)) for rel in relationships for m in [re.fullmatch(r"rId(\d+)", rel.get("Id", ""))] if m]
        next_rel = max(rel_ids, default=0) + 1
        sheet_files = [int(m.group(1)) for name in files for m in [re.fullmatch(r"xl/worksheets/sheet(\d+)\.xml", name)] if m]
        next_sheet = max(sheet_files, default=0) + 1
        generated: dict[str, bytes] = {}
        for offset, (requested_name, rows) in enumerate(sheets):
            name = requested_name
            suffix = 2
            while name in existing:
                name = f"{requested_name} {suffix}"
                suffix += 1
            existing.add(name)
            sheet_id, rel_id = next_sheet + offset, f"rId{next_rel + offset}"
            filename = f"xl/worksheets/sheet{sheet_id}.xml"
            ET.SubElement(sheet_parent, f"{{{ns_main}}}sheet", {"name": name, "sheetId": str(sheet_id), f"{{{ns_rel}}}id": rel_id})
            ET.SubElement(relationships, f"{{{ns_pkg_rel}}}Relationship", {
                "Id": rel_id, "Type": f"{ns_rel}/worksheet", "Target": f"worksheets/sheet{sheet_id}.xml"})
            ET.SubElement(content_types, f"{{{ns_ct}}}Override", {
                "PartName": f"/{filename}", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
            root = ET.Element(f"{{{ns_main}}}worksheet")
            data = ET.SubElement(root, f"{{{ns_main}}}sheetData")
            for row_index, values in enumerate(rows, 1):
                row_el = ET.SubElement(data, f"{{{ns_main}}}row", {"r": str(row_index)})
                for col_index, value in enumerate(values, 1):
                    if value is None: continue
                    cell = ET.SubElement(row_el, f"{{{ns_main}}}c", {"r": f"{get_column_letter(col_index)}{row_index}", "t": "inlineStr"})
                    inline = ET.SubElement(cell, f"{{{ns_main}}}is")
                    text = ET.SubElement(inline, f"{{{ns_main}}}t")
                    text.text = str(value)
                    if text.text != text.text.strip(): text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            generated[filename] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        generated["xl/workbook.xml"] = ET.tostring(workbook, encoding="utf-8", xml_declaration=True)
        generated["xl/_rels/workbook.xml.rels"] = ET.tostring(relationships, encoding="utf-8", xml_declaration=True)
        generated["[Content_Types].xml"] = ET.tostring(content_types, encoding="utf-8", xml_declaration=True)
        try:
            with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as zout:
                for filename, (info, payload) in files.items():
                    zout.writestr(info, generated.pop(filename, payload))
                for filename, payload in generated.items(): zout.writestr(filename, payload)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def _source(self, source_id: str):
        source = next((r for r in self.service.repository.sources() if r.sha256 == source_id), None)
        if not source:
            raise KeyError(f"Unknown source workbook {source_id!r}")
        return source

    @staticmethod
    def _builtin_pairs(path: Path, source_id: str, sheet: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
        result = extract(path, sheet, source_hash=source_id)
        wb = load_workbook(path, read_only=True, data_only=False, keep_links=False)
        ws = wb[sheet]
        def date_locator(date_value: str, measurement_cell: str):
            column = ws[measurement_cell].column
            target = date_value.replace("-", "-")
            for row in range(1, min(ws.max_row, 60) + 1):
                cell = ws.cell(row, column)
                value = cell.value
                if isinstance(value, datetime): value = value.date()
                if isinstance(value, date) and value.isoformat().startswith(target): return cell.coordinate
                if isinstance(value, str):
                    match = re.search(r"(\d{1,2})\s*[-/]\s*(20\d{2})", value)
                    if match and f"{int(match.group(2)):04d}-{int(match.group(1)):02d}" == target:
                        return cell.coordinate
            return None
        observations = result.observations
        by_location: dict[str, dict[str, Any]] = {}
        for obs in observations:
            key = " / ".join(obs.location_candidates)
            date_value = obs.date_candidates[0] if len(obs.date_candidates) == 1 else None
            bucket = by_location.setdefault(key, {"location": key, "readings": {}})
            if date_value:
                bucket["readings"].setdefault(date_value, []).append(obs)
            else:
                bucket.setdefault("undated", []).append(obs)
        pairs = []
        for bucket in by_location.values():
            dated = sorted(bucket["readings"])
            if len(dated) >= 2:
                previous_date, current_date = dated[-2:]
                prev = bucket["readings"][previous_date][-1]
                curr = bucket["readings"][current_date][-1]
            else:
                previous_date = None
                current_date = dated[-1] if dated else None
                prev = None
                curr = bucket["readings"][current_date][-1] if current_date else (bucket.get("undated") or [None])[-1]
            prev_date_cell = date_locator(previous_date, prev.source.cell) if previous_date and prev else None
            curr_date_cell = date_locator(current_date, curr.source.cell) if current_date and curr else None
            pairs.append({"location": bucket["location"], "workbook_name": path.name, "workbook_sha256": source_id,
                          "previous_thickness_mm": prev.raw_value if prev else None, "current_thickness_mm": curr.raw_value if curr else None,
                          "previous_date": previous_date, "current_date": current_date,
                          "previous_thickness_mm_source": ({"sheet": sheet, "cell": prev.source.cell} if prev else None),
                          "current_thickness_mm_source": ({"sheet": sheet, "cell": curr.source.cell} if curr else None),
                          "previous_date_source": ({"sheet": sheet, "cell": prev_date_cell} if prev_date_cell else None),
                          "current_date_source": ({"sheet": sheet, "cell": curr_date_cell} if curr_date_cell else None),
                          "previous_thickness_mm_unit": prev.raw_unit or "mm" if prev else "mm", "current_thickness_mm_unit": curr.raw_unit or "mm" if curr else "mm",
                          "date_candidates": sorted(set(c for o in (bucket.get("undated") or []) for c in o.date_candidates)),
                          "issues": (["Previous campaign date/reading is missing"] if prev is None else []) + (["Current campaign date is missing or ambiguous"] if current_date is None else [])})
        wb.close()
        return pairs

    @staticmethod
    def _custom_pairs(path: Path, source_id: str, sheet: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
        wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            if sheet not in wb.sheetnames: raise KeyError(f"Unknown exact sheet name: {sheet!r}")
            ws = wb[sheet]
            def date_cell(mapping: str, row: int):
                address = f"{mapping}{row}" if re.fullmatch(r"[A-Za-z]+", mapping.strip()) else mapping
                value = ws[address].value
                if isinstance(value, datetime): value = value.date()
                return (value.isoformat() if isinstance(value, date) else (str(value).strip() if value else None)), address
            out = []
            for r in range(profile["first_data_row"], ws.max_row + 1):
                location_parts = [ws.cell(r, c).value for c in profile["location_columns"]]
                if all(v is None or str(v).strip() == "" for v in location_parts): continue
                previous = ws.cell(r, profile["previous_thickness_column"])
                current = ws.cell(r, profile["current_thickness_column"])
                previous_date, previous_date_address = date_cell(profile["previous_date_cell"], r)
                current_date, current_date_address = date_cell(profile["current_date_cell"], r)
                location = " / ".join(str(v).strip() for v in location_parts if v is not None and str(v).strip())
                out.append({"location": location, "workbook_name": path.name, "workbook_sha256": source_id,
                            "previous_thickness_mm": previous.value, "current_thickness_mm": current.value,
                            "previous_date": previous_date, "current_date": current_date,
                            "previous_thickness_mm_source": {"sheet": sheet, "cell": previous.coordinate},
                            "current_thickness_mm_source": {"sheet": sheet, "cell": current.coordinate},
                            "previous_date_source": {"sheet": sheet, "cell": previous_date_address},
                            "current_date_source": {"sheet": sheet, "cell": current_date_address},
                            "previous_thickness_mm_unit": profile["unit"], "current_thickness_mm_unit": profile["unit"]})
            return out
        finally:
            wb.close()
