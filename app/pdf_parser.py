"""Extracción de listas de alumnos desde PDF (tablas y texto plano)."""
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import BinaryIO, Optional

import pdfplumber

HEADER_ALIASES = {
    "matricula": ("matricula", "matrícula", "mat", "id", "clave", "codigo", "código", "no. control", "num control", "control", "cuenta"),
    "nombre": ("nombre", "nombre completo", "alumno", "estudiante", "nombre del alumno"),
    "grupo": ("grupo", "asignatura", "materia", "curso"),
}
# matrícula: 4-15 caracteres alfanuméricos con al menos un dígito
ID_RE = r"(?=[A-Za-z0-9\-]*\d)[A-Za-z0-9\-]{4,15}"
LINE_RE = re.compile(rf"^\s*(?:\d{{1,3}}[.)]?\s+)?(?P<id>{ID_RE})\s+(?P<name>[^\d|;\t]+?)(?:\s+(?P<group>[A-Za-z]?\d?[A-Za-z0-9\-]{{1,12}}))?\s*$")
LINE_RE_NAME_FIRST = re.compile(rf"^\s*(?:\d{{1,3}}[.)]?\s+)?(?P<name>[^\d|;\t]+?)\s+(?P<id>{ID_RE})\s*$")
GROUP_LINE_RE = re.compile(r"(?:grupo|asignatura|materia|curso)\s*[:\-]\s*(.+)", re.I)
PERIOD_LINE_RE = re.compile(r"(?:periodo|semestre|ciclo)\s*[:\-]\s*(.+)", re.I)


@dataclass
class Row:
    matricula: str
    nombre: str
    grupo: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    rows: list[Row]
    grupo: str = ""
    periodo: str = ""
    method: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def clean(s: Optional[str]) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s.replace("\xa0", " ").replace("\u00ad", ""))
    return re.sub(r"\s+", " ", s).strip()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", clean(s).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _col_for(header: str) -> Optional[str]:
    h = _norm(header)
    for key, aliases in HEADER_ALIASES.items():
        if h in {_norm(a) for a in aliases}:
            return key
    return None


def parse_table(table: list[list[Optional[str]]]) -> list[Row]:
    """Interpreta una tabla; detecta columnas por encabezado, o por posición/contenido."""
    table = [r for r in table if r and any(clean(c) for c in r)]
    if not table:
        return []
    cols: dict[str, int] = {}
    start = 0
    for i, cell in enumerate(table[0]):
        k = _col_for(cell or "")
        if k and k not in cols:
            cols[k] = i
    if "matricula" in cols and "nombre" in cols:
        start = 1
    else:  # sin encabezado: buscar columna con IDs y la de texto más largo
        cols = {}
        ncols = max(len(r) for r in table)
        idre = re.compile(f"^{ID_RE}$")
        def score_id(j): return sum(bool(idre.match(clean(r[j]))) for r in table if j < len(r))
        def score_txt(j): return sum(len(clean(r[j])) for r in table if j < len(r) and not any(ch.isdigit() for ch in clean(r[j])))
        id_col = max(range(ncols), key=score_id)
        if score_id(id_col) == 0:
            return []
        name_col = max((j for j in range(ncols) if j != id_col), key=score_txt, default=None)
        if name_col is None:
            return []
        cols = {"matricula": id_col, "nombre": name_col}
        rest = [j for j in range(ncols) if j not in cols.values() and any(j < len(r) and clean(r[j]) and not clean(r[j]).isdigit() for r in table)]
        if rest:
            cols["grupo"] = rest[-1]
    rows = []
    for r in table[start:]:
        get = lambda k: clean(r[cols[k]]) if k in cols and cols[k] < len(r) else ""
        if not (get("matricula") or get("nombre")):
            continue
        rows.append(Row(get("matricula"), get("nombre"), get("grupo")))
    return rows


def parse_text(text: str) -> ParseResult:
    rows: list[Row] = []
    grupo = periodo = ""
    for raw in text.splitlines():
        line = clean(raw)
        if not line:
            continue
        if (m := GROUP_LINE_RE.search(line)) and not LINE_RE.match(line) and not grupo:
            grupo = clean(m.group(1)); continue
        if (m := PERIOD_LINE_RE.search(line)) and not periodo:
            periodo = clean(m.group(1)); continue
        # separadores por | ; tab
        m = LINE_RE.match(line)
        if m and len(clean(m.group("name"))) >= 3:
            rows.append(Row(m.group("id"), clean(m.group("name")), clean(m.group("group") or "")))
            continue
        m = LINE_RE_NAME_FIRST.match(line)
        if m and len(clean(m.group("name")).split()) >= 2:
            rows.append(Row(m.group("id"), clean(m.group("name"))))
    return ParseResult(rows=rows, grupo=grupo, periodo=periodo, method="text")


def validate(rows: list[Row]) -> list[Row]:
    """Marca advertencias por fila y descarta filas vacías."""
    seen: dict[str, int] = {}
    out = []
    for r in rows:
        r.matricula = clean(r.matricula).upper()
        r.nombre = clean(r.nombre)
        if not r.matricula:
            r.warnings.append("Sin matrícula")
        elif not re.fullmatch(ID_RE, r.matricula):
            r.warnings.append("Matrícula con formato inusual")
        if len(r.nombre) < 3:
            r.warnings.append("Nombre vacío o muy corto")
        if "�" in r.nombre:
            r.warnings.append("Caracteres ilegibles en el nombre")
        if r.matricula in seen:
            r.warnings.append("Matrícula duplicada")
        seen[r.matricula] = seen.get(r.matricula, 0) + 1
        out.append(r)
    return out


def parse_pdf(file: str | BinaryIO) -> ParseResult:
    header_text = []
    table_rows: list[Row] = []
    full_text = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text.append(text)
            for tbl in page.extract_tables():
                table_rows.extend(parse_table(tbl))
    text = "\n".join(full_text)
    text_result = parse_text(text)
    # Preferir tablas si dieron resultados; si no, texto.
    if table_rows:
        res = ParseResult(rows=table_rows, grupo=text_result.grupo, periodo=text_result.periodo, method="table")
    else:
        res = text_result
    if not res.rows:
        res.warnings.append("No se detectaron alumnos. ¿El PDF es un escaneo (imagen)? Se requiere OCR.")
    res.rows = validate(res.rows)
    if not res.grupo:
        gs = {r.grupo for r in res.rows if r.grupo}
        if len(gs) == 1:
            res.grupo = gs.pop()
        elif len(gs) > 1:
            res.warnings.append("El PDF contiene varios grupos: " + ", ".join(sorted(gs)))
    return res
