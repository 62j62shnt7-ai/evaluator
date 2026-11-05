"""Select supported layouts by their actual table structure, never filenames."""
from pathlib import Path
from hashlib import sha256
from openpyxl import load_workbook
from .separator import extract as separator
from .tlb import extract as pipeline
from .regions import ExtractionResult


def extract(path, sheet, *, workbook=None, source_hash=None):
    path=Path(path)
    digest=source_hash or sha256(path.read_bytes()).hexdigest()
    book=workbook if workbook is not None else load_workbook(path,data_only=False,keep_links=False)
    try:
        results=[adapter(path,sheet,workbook=book,source_hash=digest) for adapter in (separator,pipeline)]
        supported=[r for r in results if r.observations]
        if len(supported)==1:return supported[0]
        return ExtractionResult(digest,sheet,(),('Both supported layouts matched; manual layout review is required.' if supported else 'Whole sheet preserved; no supported measurement layout recognized.',))
    finally:
        if workbook is None:book.close()
