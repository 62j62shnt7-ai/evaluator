from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from openpyxl import load_workbook

from .regions import ExtractionResult, ObservationDraft, SourceLocator


def _date(v):
    if isinstance(v,datetime): return v.date().isoformat()
    if isinstance(v,date): return v.isoformat()
    return None


def extract(path: Path, sheet_name: str, *, workbook=None, source_hash=None) -> ExtractionResult:
    path=Path(path); digest=source_hash or sha256(path.read_bytes()).hexdigest()
    wb=workbook if workbook is not None else load_workbook(path,read_only=False,data_only=False,keep_links=False)
    try:
        if sheet_name not in wb.sheetnames: raise KeyError(f"unknown exact sheet name: {sheet_name!r}")
        ws=wb[sheet_name]
        from .cells import merged_value, is_measurement
        report_dates=tuple(dict.fromkeys(_date(c.value) for row in ws.iter_rows(min_row=1,max_row=min(12,ws.max_row)) for c in row if _date(c.value)))
        rows=[]; section=''; columns=[]; unresolved=[]
        for r in range(1,ws.max_row+1):
            caption=str(ws.cell(r,1).value or '').strip().upper()
            if caption in {'CMLS','NOZZLES'}:
                section=caption; columns=[]; continue
            vals=[str(ws.cell(r,c).value or '').strip().upper() for c in range(1,min(ws.max_column,15)+1)]
            if 'JOINT' in vals and ('CML NO.' in vals or 'BAND' in vals):
                section='CMLS' if 'CML NO.' in vals else 'NOZZLES'
                # Only explicitly labelled MIN columns are measurements. Never fall
                # back to column E: evaluation sheets use it for design temperature.
                min_row=r if 'MIN' in vals else r+1
                found=[]
                for c in range(1,min(ws.max_column,15)+1):
                    if str(ws.cell(min_row,c).value or '').strip().upper()!='MIN': continue
                    d=_date(merged_value(ws,r if min_row!=r else r-1,c))
                    label=str(merged_value(ws,r if min_row!=r else r-1,c) or '').strip().upper()
                    if label=='NEXT': continue
                    found.append((c,d))
                latest=max((d for _,d in found if d),default=None)
                columns=[]
                for c,d in found:
                    current=d==latest if latest else len(found)==1
                    candidates=tuple(dict.fromkeys((*report_dates,d))) if current and d else ((d,) if d else report_dates)
                    candidates=tuple(x for x in candidates if x)
                    campaign='current' if current else (d or 'undated-column-'+str(c))
                    columns.append((c,campaign,candidates))
                continue
            if not columns: continue
            if caption.startswith(('REMARK','UT - DEVICE','LEGEND','UT-DEVICE')):
                columns=[]; continue
            joint=merged_value(ws,r,1); band=merged_value(ws,r,2); location=merged_value(ws,r,3)
            if joint is None or band is None: continue
            for c,campaign,candidates in columns:
                if not is_measurement(ws.cell(r,c)): continue
                rows.append(ObservationDraft(str(ws.cell(r,c).value),'mm',SourceLocator(digest,sheet_name,ws.cell(r,c).coordinate),campaign,
                    candidates[0] if len(candidates)==1 else None,candidates,(section,str(joint).strip(),str(band).strip(),str(location or '').strip())))
        if not rows: unresolved.append('No supported tabular UT region found; drawings/images or calculation sheets require separate review.')
        if any(len(o.date_candidates)!=1 for o in rows): unresolved.append('Inspection date is missing or conflicting; resolve the affected campaign date before rate evaluation.')
        date_conflict=any(len(o.date_candidates)>1 for o in rows)
        return ExtractionResult(digest,sheet_name,tuple(rows),tuple(unresolved),date_conflict)
    finally:
        if workbook is None:wb.close()
