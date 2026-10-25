import io
from app import pdf_parser as p


def make_pdf(lines: list[str]) -> bytes:
    """PDF mínimo de una página con texto (WinAnsi, soporta acentos y ñ)."""
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = "BT /F1 11 Tf 40 780 Td 14 TL\n" + "\n".join(f"({esc(l)}) '" for l in lines) + "\nET"
    cb = content.encode("cp1252")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(cb) + cb + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)
    return out


def test_parse_text_lines_con_acentos():
    pdf = make_pdf(["Grupo: Matemáticas 3A", "Periodo: 2026-A",
                    "1 2021001 Peña Núñez, José Ángel", "2 2021002 García López María",
                    "3 2021001 Duplicado Uno"])
    r = p.parse_pdf(io.BytesIO(pdf))
    assert r.grupo == "Matemáticas 3A" and r.periodo == "2026-A"
    assert [x.matricula for x in r.rows] == ["2021001", "2021002", "2021001"]
    assert r.rows[0].nombre == "Peña Núñez, José Ángel"
    assert "Matrícula duplicada" in r.rows[2].warnings


def test_parse_table_con_encabezados():
    t = [["No.", "Matrícula", "Nombre completo", "Grupo"],
         ["1", "A0012345", "Ana  Pérez\nRuiz", "MAT-1"],
         ["2", "A0012346", "Luis Gómez", "MAT-1"], [None, None, None, None]]
    rows = p.parse_table(t)
    assert len(rows) == 2
    assert (rows[0].matricula, rows[0].nombre, rows[0].grupo) == ("A0012345", "Ana Pérez Ruiz", "MAT-1")


def test_parse_table_sin_encabezados():
    t = [["1", "Ana Pérez", "20210001"], ["2", "Luis Gómez", "20210002"]]
    rows = p.parse_table(t)
    assert [r.matricula for r in rows] == ["20210001", "20210002"]
    assert rows[1].nombre == "Luis Gómez"


def test_validate_advertencias():
    rows = p.validate([p.Row("", "Al"), p.Row("12", "Nombre Valido")])
    assert "Sin matrícula" in rows[0].warnings and "Nombre vacío o muy corto" in rows[0].warnings
    assert "Matrícula con formato inusual" in rows[1].warnings


def test_pdf_sin_alumnos():
    r = p.parse_pdf(io.BytesIO(make_pdf(["Documento sin lista"])))
    assert r.rows == [] and r.warnings
