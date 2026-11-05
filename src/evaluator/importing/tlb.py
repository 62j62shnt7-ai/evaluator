from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
import re
from openpyxl import load_workbook

from .cells import merged_value, is_measurement
from .regions import ExtractionResult, ObservationDraft, SourceLocator


def _date(v):
    if isinstance(v, datetime): return v.date().isoformat()
    if isinstance(v, date): return v.isoformat()
    return None


def _dated_columns(ws, digest, sheet_name):
    """Read literal UT values from columns whose inspection dates are in the header area."""
    top = min(15, ws.max_row)
    headers = []
    for row in range(1, top + 1):
        values = [str(ws.cell(row, c).value or '').strip().casefold() for c in range(1, min(ws.max_column, 30) + 1)]
        if 'joint' not in values or 'band' not in values:
            continue
        date_rows = []
        for date_row in range(1, top + 1):
            dated = [(c, _date(ws.cell(date_row, c).value)) for c in range(1, ws.max_column + 1)]
            dated = [(c, value) for c, value in dated if value]
            if len(dated) < 2:
                continue
            measurement_columns = []
            for c, _ in dated:
                heading = str(merged_value(ws, row, c) or '').upper()
                if 'MIN' in heading and 'MAX' not in heading:
                    measurement_columns.append(c)
            if len(measurement_columns) >= 2:
                date_rows.append((date_row, {c: value for c, value in dated if c in measurement_columns}))
        if date_rows:
            # Prefer the date row with the most aligned date/reading columns.
            date_row, dated_columns = max(date_rows, key=lambda item: (len(item[1]), -abs(item[0] - row)))
            headers.append((row, date_row, dated_columns))
    if not headers:
        return ()

    header_row, date_row, dated_columns = headers[0]
    output = []
    section = ''
    for r in range(1, ws.max_row + 1):
        label = ws.cell(r, 1).value
        section_match = re.match(r'\s*SECTION\s+\d+', str(label or ''), re.I)
        if section_match:
            section = str(label).strip()
        if r <= max(header_row, date_row):
            continue
        joint, band = merged_value(ws, r, 1), merged_value(ws, r, 2)
        if joint is None or band is None:
            continue
        if isinstance(joint, str): joint = joint.strip()
        if isinstance(band, str): band = band.strip()
        for column, inspection_date in dated_columns.items():
            cell = ws.cell(r, column)
            if not is_measurement(cell):
                continue
            campaign = inspection_date
            output.append(ObservationDraft(
                str(cell.value), 'mm', SourceLocator(digest, sheet_name, cell.coordinate), campaign,
                inspection_date, (inspection_date,),
                (section, str(joint).strip(), str(band).strip()),
            ))
    return tuple(output)


def extract(path: Path, sheet_name: str, *, workbook=None, source_hash=None) -> ExtractionResult:
    path=Path(path); digest=source_hash or sha256(path.read_bytes()).hexdigest()
    wb=workbook if workbook is not None else load_workbook(path,read_only=False,data_only=False,keep_links=False)
    try:
        if sheet_name not in wb.sheetnames: raise KeyError(f"unknown exact sheet name: {sheet_name!r}")
        ws=wb[sheet_name]
        dated_columns = _dated_columns(ws, digest, sheet_name)
        if dated_columns:
            return ExtractionResult(digest, sheet_name, dated_columns, (), False)
        report_dates=tuple(dict.fromkeys(_date(ws.cell(1,c).value) for c in range(1,ws.max_column+1) if _date(ws.cell(1,c).value)))
        title_match=re.search(r'(\d{1,2})\s*[-/]\s*(20\d{2})',sheet_name)
        title_month=f"{int(title_match.group(2)):04d}-{int(title_match.group(1)):02d}" if title_match else None
        title_conflict=bool(title_month and report_dates and report_dates[0][:7]!=title_month)
        section=''; header=None; output=[]; notes=[]; campaign_columns={}
        for r in range(1,ws.max_row+1):
            a=ws.cell(r,1).value
            if isinstance(a,str) and re.match(r'\s*SECTION\s+\d+',a,re.I): section=a.strip()
            values=[ws.cell(r,c).value for c in range(1,min(ws.max_column,19)+1)]
            normalized=[str(v).strip().lower() if v is not None else '' for v in values]
            if 'joint' in normalized and 'band' in normalized and ('nom d' in normalized or 'nominal thickness' in normalized):
                header=r
                for column in range(5,min(ws.max_column,19)+1):
                    raw_header=str(ws.cell(r,column).value or '').strip()
                    if not raw_header.lower().startswith('min'): continue
                    text=raw_header
                    if '\n' in text: text=text.splitlines()[-1].strip()
                    if text and text.lower() not in {'max','t nom','comments'}:
                        campaign_columns.setdefault(text,set()).add(column)
                continue
            if header is None or r<=header: continue
            joint=merged_value(ws,r,1); band=merged_value(ws,r,2)
            if joint is None and band is None: continue
            if isinstance(joint,str): joint=joint.strip()
            # The adjacent header row can place the date beneath a merged "min" heading.
            for c in range(5,min(ws.max_column,19)+1):
                raw=ws.cell(r,c).value
                if not is_measurement(ws.cell(r,c)): continue
                label=ws.cell(header,c).value
                label_text=str(label or '').strip()
                if not label_text.lower().startswith('min'): continue
                campaign=label_text
                if '\n' in campaign: campaign=campaign.splitlines()[-1].strip()
                if not campaign or campaign.lower() in {'max','t nom','comments'}: continue
                match=re.search(r'(\d{1,2})\s*[-/]\s*(20\d{2})',campaign)
                campaign_date=(f"{int(match.group(2)):04d}-{int(match.group(1)):02d}" if match else None)
                dates=(report_dates if campaign_date and report_dates and report_dates[0][:7]==campaign_date else ((campaign_date,report_dates[0]) if campaign_date and campaign_date==title_month and title_conflict else ((campaign_date,) if campaign_date else ())))
                # A dated reading-column header takes precedence over report metadata.
                dates=(campaign_date,) if campaign_date else dates
                selected=campaign_date if campaign_date else None
                output.append(ObservationDraft(str(raw), 'mm', SourceLocator(digest,sheet_name,ws.cell(r,c).coordinate), campaign,
                    selected, dates, (section,str(joint if joint is not None else '').strip(),str(band if band is not None else '').strip())))
            # A subsequent section header resets the table; repeated tables can be found later.
            if isinstance(a,str) and re.match(r'\s*SECTION\s+\d+',a,re.I): header=None
        if not output: notes.append('No recognized joint/band/minimum table found; sheet remains unresolved.')
        if len(report_dates)>1: notes.append('Conflicting report date candidates require review.')
        if title_conflict: notes.append(f"Sheet campaign hint {title_month} conflicts with explicit report date {report_dates[0]}; affected current readings need date resolution.")
        repeated={label:cols for label,cols in campaign_columns.items() if len(cols)>1}
        if repeated: notes.append('Repeated campaign headers retained as separate cell observations; confirm whether columns are distinct locations or duplicate labels.')
        if any(not o.date_candidates for o in output): notes.append('Some historical columns have no explicit campaign date; those observations need date resolution.')
        return ExtractionResult(digest,sheet_name,tuple(output),tuple(notes),len(report_dates)>1 or title_conflict)
    finally:
        if workbook is None:wb.close()
