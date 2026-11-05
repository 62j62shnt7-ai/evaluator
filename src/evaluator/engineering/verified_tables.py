"""Exact-match access to source-checked material stress and pipe-dimension rows."""

from __future__ import annotations

import json
import hashlib
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class ReferenceLookupError(ValueError):
    pass


def _material_token(value: Any) -> str:
    token = re.sub(r"[^A-Z0-9]", "", str(value).upper()).removeprefix("ASTM")
    return token.replace("GRADE", "").replace("GR", "")


def _decimal(value: Any, label: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ReferenceLookupError(f"Invalid exact lookup value for {label}: {value!r}") from None


class VerifiedTables:
    """Read checked JSON rows without interpolation, substitution, or extrapolation."""

    def __init__(self, data_dir: str | Path | None = None, code_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parents[1] / "data"
        self.code_dir = Path(code_dir) if code_dir else Path(__file__).parents[3] / "sources" / "codes"
        self._stresses = json.loads((self.data_dir / "material_stresses.json").read_text(encoding="utf-8"))
        self._dimensions = json.loads((self.data_dir / "pipe_dimensions.json").read_text(encoding="utf-8"))
        self._validate_rows()

    def _validate_rows(self) -> None:
        for row in self._stresses:
            if not row.get("verification") or not row.get("source_sha256") or not row.get("reference"):
                raise ReferenceLookupError("Material stress row lacks verification or source provenance")
        for row in self._dimensions:
            if not row.get("source_sha256") or not row.get("reference") or row.get("pdf_page") is None:
                raise ReferenceLookupError("Pipe dimension row lacks code/table/page/hash provenance")

    @staticmethod
    def _provenance(row: dict[str, Any], code: str, edition: str, table: str) -> dict[str, Any]:
        return {
            "source_type": "code_table",
            "code": code,
            "edition": edition,
            "table": table,
            "page": row.get("pdf_page"),
            "reference": row.get("reference"),
            "source_sha256": row["source_sha256"],
            "verification": row.get("verification", "source-checked row"),
        }

    def _verify_source(self, row: dict[str, Any], filename: str) -> None:
        source = self.code_dir / filename
        if not source.is_file():
            raise ReferenceLookupError(
                f"Verified lookup withheld: source PDF {source} is unavailable"
            )
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != row["source_sha256"]:
            raise ReferenceLookupError(
                f"Verified lookup withheld: source hash for {source.name} does not match the checked table row"
            )

    def allowable_stress(
        self, material: str, product_form: str, code: str, edition: str, temperature_F: Any
    ) -> dict[str, Any]:
        temperature = _decimal(temperature_F, "temperature_F")
        material_key = _material_token(material)
        matches = [
            row for row in self._stresses
            if row["material_token"] == material_key
            and row["product_form"] == product_form
            and row["code_family"] == code
            and row["code_edition"] == str(edition)
            and _decimal(row["temperature_F"], "table temperature") == temperature
        ]
        if len(matches) != 1:
            available = sorted({row["temperature_F"] for row in self._stresses
                                if row["material_token"] == material_key
                                and row["product_form"] == product_form
                                and row["code_family"] == code
                                and row["code_edition"] == str(edition)})
            raise ReferenceLookupError(
                f"No exact allowable-stress match for {material} ({product_form}), {code} {edition}, "
                f"{temperature}°F, Table A-1C; available exact temperatures: {available or 'none'}"
            )
        row = dict(matches[0])
        self._verify_source(row, "B31_3_2024.pdf")
        row["provenance"] = self._provenance(row, code, str(edition), "Table A-1C")
        return row

    def pipe_dimension(self, family: str, nps: str, schedule: str) -> dict[str, Any]:
        matches = [
            row for row in self._dimensions
            if row["family"] == family and row["nps"] == str(nps) and row["schedule"] == str(schedule)
        ]
        if len(matches) != 1:
            raise ReferenceLookupError(
                f"No exact API RP 574 Annex B dimension row for family={family}, NPS={nps}, schedule={schedule}; "
                "no neighboring size or schedule is substituted"
            )
        row = dict(matches[0])
        if row.get("issues"):
            raise ReferenceLookupError(
                f"API RP 574 Annex B, page {row['pdf_page']} row for family={family}, NPS={nps}, "
                f"schedule={schedule} is withheld for source discrepancy: {', '.join(row['issues'])}"
            )
        self._verify_source(row, "RP_574_E5_EN_wA1.pdf")
        row["provenance"] = self._provenance(row, "API RP 574", "5th edition + Addendum 1", "Annex B, Table B.1")
        return row
