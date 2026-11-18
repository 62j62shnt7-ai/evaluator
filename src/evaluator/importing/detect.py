"""Select supported layouts by their actual table structure, never filenames."""
from pathlib import Path
from hashlib import sha256
from openpyxl.reader.excel import ExcelReader
from .separator import extract as separator
from .tlb import extract as pipeline
from .regions import ExtractionResult


def extract(path, sheet, *, workbook=None, source_hash=None):
    path=Path(path)
    digest=source_hash or sha256(path.read_bytes()).hexdigest()
    book = workbook if workbook is not None else _load_selected_sheet(path, sheet)
    try:
        results=[adapter(path,sheet,workbook=book,source_hash=digest) for adapter in (separator,pipeline)]
        supported=[r for r in results if r.observations]
        if len(supported)==1:return supported[0]
        return ExtractionResult(digest,sheet,(),('Both supported layouts matched; manual layout review is required.' if supported else 'Whole sheet preserved; no supported measurement layout recognized.',))
    finally:
        if workbook is None:book.close()


def _load_selected_sheet(path, name):
    class SelectedSheetReader(ExcelReader):
        def read_worksheets(self):
            sheets = tuple((sheet, relation) for sheet, relation in self.parser.find_sheets()
                           if sheet.name == name)
            if not sheets:
                raise KeyError(f'unknown exact sheet name: {name!r}')
            self.parser.find_sheets = lambda: iter(sheets)
            # The adapters read cell coordinates directly. Workbook-scoped
            # defined names can point to tabs outside the selected sheet.
            self.parser.assign_names = lambda: None
            super().read_worksheets()

    reader = SelectedSheetReader(path, data_only=False, keep_links=False)
    try:
        reader.read()
        return reader.wb
    finally:
        reader.archive.close()
