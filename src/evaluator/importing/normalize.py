from dataclasses import dataclass
from decimal import Decimal
from dataclasses import dataclass, field
import json
import sqlite3
from evaluator.storage.database import connection
import hashlib


FACTORS = {"mm": (Decimal("1"), Decimal("0")), "in": (Decimal("25.4"), Decimal("0")),
           "C": (Decimal("1"), Decimal("0")), "F": (Decimal("0.5555555555555555555555555556"), Decimal("-17.77777777777777777777777778")),
           "psi": (Decimal("1"), Decimal("0")), "MPa": (Decimal("145.03773773020923"), Decimal("0"))}


def convert(value: str, unit: str, target: str) -> Decimal:
    pairs = {("mm", "mm"), ("in", "mm"), ("C", "C"), ("F", "C"), ("psi", "psi"), ("MPa", "psi")}
    if (unit, target) not in pairs:
        raise ValueError(f"unsupported unit conversion: {unit} to {target}")
    scale, offset = FACTORS[unit]
    return Decimal(value) * scale + offset


@dataclass(frozen=True)
class CoverageSummary:
    detected: int
    imported: int
    excluded: int
    unresolved: int

    def __post_init__(self):
        if self.detected != self.imported + self.excluded + self.unresolved:
            raise ValueError("coverage counts must reconcile")


@dataclass(frozen=True)
class RegionStatus:
    region_id: str
    status: str
    reason: str = ""
    observations: tuple[dict, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if self.status not in {"imported", "excluded", "unresolved"}:
            raise ValueError("region status must be imported, excluded or unresolved")
        if self.status != "imported" and not self.reason:
            raise ValueError("excluded and unresolved regions require a reason")


@dataclass(frozen=True)
class ExtractionResult:
    source_id: str
    regions: tuple[RegionStatus, ...]


@dataclass(frozen=True)
class ImportSummary:
    revision: int
    imported: int
    regions: int


def persist_extraction(repository, result: ExtractionResult, expected_revision: int) -> ImportSummary:
    with connection(repository.path) as db:
        db.execute("BEGIN IMMEDIATE")
        rev = int(db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0])
        existing = db.execute("SELECT region_id,status,reason FROM regions WHERE source_id=? ORDER BY region_id", (result.source_id,)).fetchall()
        proposed = sorted((r.region_id,r.status,r.reason) for r in result.regions)
        if [tuple(r) for r in existing] == proposed and existing:
            stored = db.execute("SELECT observation_id,payload FROM observations WHERE source_id=? ORDER BY observation_id", (result.source_id,)).fetchall()
            incoming = sorted((str(o['id']),json.dumps(o,sort_keys=True,ensure_ascii=False)) for r in result.regions for o in r.observations)
            if [tuple(r) for r in stored] == incoming:
                return ImportSummary(rev, sum(r.status == 'imported' for r in result.regions), len(result.regions))
        if rev != expected_revision:
            raise ValueError(f"stale revision: expected {expected_revision}, found {rev}")
        db.execute("DELETE FROM regions WHERE source_id=?", (result.source_id,))
        db.execute("DELETE FROM observations WHERE source_id=?", (result.source_id,))
        for region in result.regions:
            db.execute("INSERT INTO regions VALUES (?,?,?,?)", (result.source_id,region.region_id,region.status,region.reason))
            for obs in region.observations:
                if "id" not in obs:
                    raise ValueError("observation is missing stable id")
                db.execute("INSERT INTO observations VALUES (?,?,?)", (result.source_id,str(obs['id']),json.dumps(obs,sort_keys=True,ensure_ascii=False)))
        new_rev = rev + 1
        db.execute("UPDATE metadata SET value=? WHERE key='revision'", (str(new_rev),))
    return ImportSummary(new_rev,sum(r.status == 'imported' for r in result.regions),len(result.regions))


def coverage(repository, source_id: str) -> CoverageSummary:
    with connection(repository.path) as db:
        rows = db.execute("SELECT status,COUNT(*) FROM regions WHERE source_id=? GROUP BY status", (source_id,)).fetchall()
    counts = dict(rows)
    return CoverageSummary(sum(counts.values()),counts.get('imported',0),counts.get('excluded',0),counts.get('unresolved',0))


def observation_id(source_hash: str, sheet: str, cell_or_object: str, campaign: str) -> str:
    """Stable provenance-based ID; changed source bytes naturally create new IDs."""
    key='\0'.join((source_hash,sheet,cell_or_object,campaign)).encode('utf-8')
    return hashlib.sha256(key).hexdigest()


def measurement_summary(readings):
    """Return minimum and all contributing IDs without discarding source readings."""
    readings=list(readings)
    if not readings: return None, ()
    minimum=min(value for _,value in readings)
    contributors=tuple(sorted(identifier for identifier,value in readings if value==minimum))
    return minimum,contributors
