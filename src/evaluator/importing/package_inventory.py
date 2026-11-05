from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class SheetInfo:
    name: str
    state: str
    relationship_id: str
    merged_regions: tuple[str, ...] = ()
    dimensions: str = ""


@dataclass(frozen=True)
class WorkbookInventory:
    sheets: tuple[SheetInfo, ...]
    objects: tuple[str, ...]
    links: tuple[str, ...]
    formulas: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self):
        return {"sheets": [asdict(s) for s in self.sheets], "objects": list(self.objects),
                "links": list(self.links), "formulas": list(self.formulas), "warnings": list(self.warnings)}


def inventory(path: Path, max_bytes: int = 100_000_000, max_expanded: int = 500_000_000) -> WorkbookInventory:
    path = Path(path)
    if path.stat().st_size > max_bytes:
        raise ValueError("workbook exceeds compressed size limit")
    try:
        with ZipFile(path) as z:
            entries = z.infolist()
            if sum(i.file_size for i in entries) > max_expanded:
                raise ValueError("workbook exceeds expanded size limit")
            bad = z.testzip()
            if bad:
                raise ValueError(f"corrupt workbook member: {bad}")
            root = ET.fromstring(z.read("xl/workbook.xml"))
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                  "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
            rel_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
            rel_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            rels = {e.attrib.get("Id"):e.attrib.get("Target", "") for e in rel_root}
            sheets_list = []
            for e in root.findall("m:sheets/m:sheet", ns):
                rid = e.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
                target = rels.get(rid, "")
                sheet_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
                try:
                    sheet_xml = ET.fromstring(z.read(sheet_path))
                    dim = sheet_xml.find("m:dimension", ns)
                    merges = tuple(x.attrib.get("ref", "") for x in sheet_xml.findall("m:mergeCells/m:mergeCell", ns))
                    dimension = dim.attrib.get("ref", "") if dim is not None else ""
                except KeyError:
                    merges, dimension = (), ""
                sheets_list.append(SheetInfo(e.attrib["name"], e.attrib.get("state", "visible"), rid, merges, dimension))
            sheets = tuple(sheets_list)
            formulas = []
            for name in z.namelist():
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    try:
                        sheet = ET.fromstring(z.read(name))
                        for cell in sheet.findall(".//m:c", ns):
                            f = cell.find("m:f", ns)
                            if f is not None:
                                formulas.append(f"{name}:{cell.attrib.get('r','')}={f.text or ''}")
                    except ET.ParseError:
                        raise ValueError(f"malformed worksheet XML: {name}")
            objects = tuple(n for n in z.namelist() if n.startswith("xl/media/") or "/drawings/" in n or "/diagrams/" in n)
            links = tuple(n for n in z.namelist() if n.startswith("xl/externalLinks/"))
            links += tuple(f"{n}:{e.attrib.get('Target','')}" for n in z.namelist() if n.endswith('.rels')
                           for e in ET.fromstring(z.read(n)) if e.attrib.get('TargetMode') == 'External')
            warns = ("Package objects require visual review; inventory does not certify drawing completeness.",) if objects else ()
            return WorkbookInventory(sheets, objects, links, tuple(formulas), warns)
    except BadZipFile as exc:
        raise ValueError("invalid XLSX/XLSM ZIP package") from exc
