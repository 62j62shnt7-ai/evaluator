from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLocator:
    file_hash: str
    sheet: str
    cell: str


@dataclass(frozen=True)
class ObservationDraft:
    raw_value: str
    raw_unit: str | None
    source: SourceLocator
    campaign_label: str
    inspection_date: str | None
    date_candidates: tuple[str, ...]
    location_candidates: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionResult:
    source_hash: str
    sheet: str
    observations: tuple[ObservationDraft, ...]
    unresolved: tuple[str, ...]
    date_conflict: bool = False
