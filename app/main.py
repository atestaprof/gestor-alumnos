import csv
import io
from datetime import date
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from pathlib import Path

from . import models as m, grading, pdf_parser
from .database import Base, engine, get_db, migrate

Base.metadata.create_all(engine)
migrate()
app = FastAPI(title="Gestor de Alumnos")


# ---------- Schemas ----------
class GrupoIn(BaseModel):
    nombre: str = Field(min_length=1)
    periodo: str = ""


class AlumnoIn(BaseModel):
    matricula: str = Field(min_length=1)
    nombre: str = Field(min_length=1)


class ImportConfirm(GrupoIn):
    alumnos: list[AlumnoIn]


class CriterioIn(BaseModel):
    pct_asistencia: float
    pct_tareas: float
    pct_practicas: float
    pct_examenes: float


class AsistenciaIn(BaseModel):
    fecha: date
    registros: dict[int, m.EstadoAsistencia]  # alumno_id -> estado


class EvaluacionIn(BaseModel):
    tipo: m.TipoEvaluacion
    titulo: str = Field(min_length=1)
    fecha: date
    max_puntos: float = Field(gt=0, default=100)
    puntajes: dict[int, Optional[float]] = {}


class PuntajesIn(BaseModel):
    puntajes: dict[int, Optional[float]]


def _grupo(db: Session, gid: int) -> m.Grupo:
    g = db.get(m.Grupo, gid)
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    return g


def _criterio(db: Session, g: m.Grupo) -> m.CriterioEvaluacion:
    if not g.criterio:
        g.criterio = m.CriterioEvaluacion(grupo_id=g.id)
        db.commit()
    return g.criterio


def _crear_grupo(db, nombre, periodo) -> m.Grupo:
    if db.scalar(select(m.Grupo).where(m.Grupo.nombre == nombre, m.Grupo.periodo == periodo)):
        raise HTTPException(409, "Ya existe un grupo con ese nombre y periodo")
    g = m.Grupo(nombre=nombre, periodo=periodo, criterio=m.CriterioEvaluacion())
    db.add(g)
    db.flush()
    return g


# ---------- Grupos ----------
@app.get("/api/grupos")
def listar_grupos(db: Session = Depends(get_db)):
    return [{"id": g.id, "nombre": g.nombre, "periodo": g.periodo, "alumnos": len(g.alumnos)}
            for g in db.scalars(select(m.Grupo).order_by(m.Grupo.nombre))]


@app.post("/api/grupos", status_code=201)
def crear_grupo(data: GrupoIn, db: Session = Depends(get_db)):
    g = _crear_grupo(db, data.nombre.strip(), data.periodo.strip())
    db.commit()
    return {"id": g.id}


@app.delete("/api/grupos/{gid}", status_code=204)
def borrar_grupo(gid: int, db: Session = Depends(get_db)):
    db.delete(_grupo(db, gid))
    db.commit()


@app.get("/api/grupos/{gid}/alumnos")
def listar_alumnos(gid: int, db: Session = Depends(get_db)):
    g = _grupo(db, gid)
    return [{"id": a.id, "matricula": a.matricula, "nombre": a.nombre}
            for a in sorted(g.alumnos, key=lambda a: a.nombre)]


# ---------- Importación PDF ----------
@app.post("/api/import/preview")
async def preview_pdf(file: UploadFile = File(...)):
    data = await file.read()
    try:
        res = pdf_parser.parse_pdf(io.BytesIO(data))
    except Exception as e:
        raise HTTPException(400, f"No se pudo leer el PDF: {e}")
    return res.to_dict()


@app.post("/api/import/confirm", status_code=201)
def confirmar_import(data: ImportConfirm, db: Session = Depends(get_db)):
    mats = [a.matricula.strip().upper() for a in data.alumnos]
    if len(set(mats)) != len(mats):
        raise HTTPException(422, "Hay matrículas duplicadas")
    if not mats:
        raise HTTPException(422, "No hay alumnos para importar")
    g = _crear_grupo(db, data.nombre.strip(), data.periodo.strip())
    for a, mat in zip(data.alumnos, mats):
        db.add(m.Alumno(matricula=mat, nombre=a.nombre.strip(), grupo_id=g.id))
    db.commit()
    return {"id": g.id, "alumnos": len(mats)}


# ---------- Criterios ----------
@app.get("/api/grupos/{gid}/criterios")
def get_criterios(gid: int, db: Session = Depends(get_db)):
    c = _criterio(db, _grupo(db, gid))
    return {"pct_asistencia": c.pct_asistencia, "pct_tareas": c.pct_tareas,
            "pct_practicas": c.pct_practicas, "pct_examenes": c.pct_examenes}


@app.put("/api/grupos/{gid}/criterios")
def set_criterios(gid: int, data: CriterioIn, db: Session = Depends(get_db)):
    try:
        grading.validar_pesos(data.pct_asistencia, data.pct_tareas, data.pct_practicas, data.pct_examenes)
    except grading.PesosInvalidos as e:
        raise HTTPException(422, str(e))
    c = _criterio(db, _grupo(db, gid))
    c.pct_asistencia, c.pct_tareas = data.pct_asistencia, data.pct_tareas
    c.pct_practicas, c.pct_examenes = data.pct_practicas, data.pct_examenes
    db.commit()
    return data


# ---------- Asistencia ----------
@app.get("/api/grupos/{gid}/asistencias")
def get_asistencia(gid: int, fecha: date, db: Session = Depends(get_db)):
    g = _grupo(db, gid)
    ids = [a.id for a in g.alumnos]
    rows = db.scalars(select(m.Asistencia).where(m.Asistencia.alumno_id.in_(ids), m.Asistencia.fecha == fecha))
    return {r.alumno_id: r.estado.value for r in rows}


@app.get("/api/grupos/{gid}/asistencias/fechas")
def fechas_asistencia(gid: int, db: Session = Depends(get_db)):
    g = _grupo(db, gid)
    ids = [a.id for a in g.alumnos]
    q = select(m.Asistencia.fecha).where(m.Asistencia.alumno_id.in_(ids)).distinct().order_by(m.Asistencia.fecha)
    return [d.isoformat() for d in db.scalars(q)]


@app.put("/api/grupos/{gid}/asistencias")
def guardar_asistencia(gid: int, data: AsistenciaIn, db: Session = Depends(get_db)):
    g = _grupo(db, gid)
    valid = {a.id for a in g.alumnos}
    if set(data.registros) - valid:
        raise HTTPException(422, "Alumno no pertenece al grupo")
    existing = {r.alumno_id: r for r in db.scalars(
        select(m.Asistencia).where(m.Asistencia.alumno_id.in_(valid), m.Asistencia.fecha == data.fecha))}
    for aid, est in data.registros.items():
        if aid in existing:
            existing[aid].estado = est
        else:
            db.add(m.Asistencia(fecha=data.fecha, alumno_id=aid, estado=est))
    db.commit()
    return {"guardados": len(data.registros)}


# ---------- Evaluaciones ----------
def _guardar_puntajes(db, ev: m.Evaluacion, puntajes, valid_ids):
    if set(puntajes) - valid_ids:
        raise HTTPException(422, "Alumno no pertenece al grupo")
    existing = {c.alumno_id: c for c in ev.calificaciones}
    for aid, p in puntajes.items():
        if p is not None and not (0 <= p <= ev.max_puntos):
            raise HTTPException(422, f"Puntaje fuera de rango (0-{ev.max_puntos})")
        if p is None:
            if aid in existing:
                db.delete(existing[aid])
        elif aid in existing:
            existing[aid].puntaje = p
        else:
            db.add(m.Calificacion(evaluacion_id=ev.id, alumno_id=aid, puntaje=p))


@app.get("/api/grupos/{gid}/evaluaciones")
def listar_evals(gid: int, db: Session = Depends(get_db)):
    g = _grupo(db, gid)
    return [{"id": e.id, "tipo": e.tipo.value, "titulo": e.titulo, "fecha": e.fecha.isoformat(),
             "max_puntos": e.max_puntos, "puntajes": {c.alumno_id: c.puntaje for c in e.calificaciones}}
            for e in sorted(g.evaluaciones, key=lambda e: (e.fecha, e.id))]


@app.post("/api/grupos/{gid}/evaluaciones", status_code=201)
def crear_eval(gid: int, data: EvaluacionIn, db: Session = Depends(get_db)):
    g = _grupo(db, gid)
    ev = m.Evaluacion(grupo_id=gid, tipo=data.tipo, titulo=data.titulo.strip(), fecha=data.fecha, max_puntos=data.max_puntos)
    db.add(ev)
    db.flush()
    _guardar_puntajes(db, ev, data.puntajes, {a.id for a in g.alumnos})
    db.commit()
    return {"id": ev.id}


@app.put("/api/evaluaciones/{eid}/calificaciones")
def actualizar_puntajes(eid: int, data: PuntajesIn, db: Session = Depends(get_db)):
    ev = db.get(m.Evaluacion, eid)
    if not ev:
        raise HTTPException(404, "Evaluación no encontrada")
    _guardar_puntajes(db, ev, data.puntajes, {a.id for a in ev.grupo.alumnos})
    db.commit()
    return {"ok": True}


@app.delete("/api/evaluaciones/{eid}", status_code=204)
def borrar_eval(eid: int, db: Session = Depends(get_db)):
    ev = db.get(m.Evaluacion, eid)
    if not ev:
        raise HTTPException(404, "Evaluación no encontrada")
    db.delete(ev)
    db.commit()


# ---------- Sábana ----------
def calcular_sabana(db: Session, g: m.Grupo, pesos=None):
    c = _criterio(db, g)
    pa, pt, pp, pe = pesos or (c.pct_asistencia, c.pct_tareas, c.pct_practicas, c.pct_examenes)
    grading.validar_pesos(pa, pt, pp, pe)
    ids = [a.id for a in g.alumnos]
    asist: dict[int, list[str]] = {i: [] for i in ids}
    for r in db.scalars(select(m.Asistencia).where(m.Asistencia.alumno_id.in_(ids))):
        asist[r.alumno_id].append(r.estado.value)
    evals = g.evaluaciones
    out = []
    for a in sorted(g.alumnos, key=lambda a: a.nombre):
        est = asist[a.id]
        punt = {c_.evaluacion_id: c_.puntaje for c_ in a.calificaciones}
        def prom(tipo):
            return grading.promedio_evaluaciones((punt.get(e.id), e.max_puntos) for e in evals if e.tipo == tipo)
        pas, pta, ppr, pex = (grading.promedio_asistencia(est), prom(m.TipoEvaluacion.TAREA),
                              prom(m.TipoEvaluacion.PRACTICA), prom(m.TipoEvaluacion.EXAMEN))
        out.append({
            "alumno_id": a.id, "matricula": a.matricula, "nombre": a.nombre,
            "presentes": est.count("Presente"), "retardos": est.count("Retardo"),
            "faltas": est.count("Falta"), "justificados": est.count("Justificado"),
            "prom_asistencia": None if pas is None else round(pas, 2),
            "prom_tareas": None if pta is None else round(pta, 2),
            "prom_practicas": None if ppr is None else round(ppr, 2),
            "prom_examenes": None if pex is None else round(pex, 2),
            "final": grading.calificacion_final(pa, pt, pp, pe, pas, pta, ppr, pex),
        })
    return {"pesos": {"pct_asistencia": pa, "pct_tareas": pt, "pct_practicas": pp, "pct_examenes": pe}, "alumnos": out}


@app.get("/api/grupos/{gid}/sabana")
def sabana(gid: int, asistencia: Optional[float] = None, tareas: Optional[float] = None,
           practicas: Optional[float] = None, examenes: Optional[float] = None, db: Session = Depends(get_db)):
    """Con los 3 parámetros opcionales se simula otra ponderación sin guardarla."""
    g = _grupo(db, gid)
    pesos = (asistencia, tareas, practicas, examenes) if None not in (asistencia, tareas, practicas, examenes) else None
    try:
        return calcular_sabana(db, g, pesos)
    except grading.PesosInvalidos as e:
        raise HTTPException(422, str(e))


# ---------- Exportación ----------
@app.get("/api/grupos/{gid}/export")
def exportar(gid: int, formato: str = Query("xlsx", pattern="^(xlsx|csv)$"), db: Session = Depends(get_db)):
    g = _grupo(db, gid)
    sab = calcular_sabana(db, g)
    head = ["Matrícula", "Nombre", "Presentes", "Retardos", "Faltas", "Justificados",
            "Prom. Asistencia", "Prom. Tareas", "Prom. Prácticas", "Prom. Exámenes", "Final"]
    keys = ["matricula", "nombre", "presentes", "retardos", "faltas", "justificados",
            "prom_asistencia", "prom_tareas", "prom_practicas", "prom_examenes", "final"]
    rows = [[a[k] for k in keys] for a in sab["alumnos"]]
    base = f"{g.nombre}_{g.periodo}".replace(" ", "_").replace("/", "-")
    if formato == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(head); w.writerows(rows)
        data = io.BytesIO(("\ufeff" + buf.getvalue()).encode("utf-8"))  # BOM para Excel
        media, fn = "text/csv", f"{base}.csv"
    else:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active; ws.title = "Sábana"
        ws.append(head); ws.append([]); ws.delete_rows(2)
        for r in rows: ws.append(r)
        p = sab["pesos"]
        ws.append([]); ws.append(["Ponderación", f"Asist {p['pct_asistencia']}% / Tareas {p['pct_tareas']}% / Prácticas {p['pct_practicas']}% / Exámenes {p['pct_examenes']}%"])
        # Histórico de asistencia
        wa = wb.create_sheet("Asistencias")
        alumnos = sorted(g.alumnos, key=lambda a: a.nombre)
        ids = [a.id for a in alumnos]
        regs = list(db.scalars(select(m.Asistencia).where(m.Asistencia.alumno_id.in_(ids))))
        fechas = sorted({r.fecha for r in regs})
        mp = {(r.alumno_id, r.fecha): r.estado.value for r in regs}
        wa.append(["Matrícula", "Nombre"] + [f.isoformat() for f in fechas])
        for a in alumnos:
            wa.append([a.matricula, a.nombre] + [mp.get((a.id, f), "") for f in fechas])
        # Histórico de calificaciones
        wc = wb.create_sheet("Calificaciones")
        evs = sorted(g.evaluaciones, key=lambda e: (e.fecha, e.id))
        wc.append(["Matrícula", "Nombre"] + [f"{e.tipo.value}: {e.titulo} (/{e.max_puntos:g})" for e in evs])
        for a in alumnos:
            pm = {c.evaluacion_id: c.puntaje for c in a.calificaciones}
            wc.append([a.matricula, a.nombre] + [pm.get(e.id, "") for e in evs])
        for s in wb.worksheets:
            for cell in s[1]: cell.font = Font(bold=True)
            s.column_dimensions["B"].width = 36
        data = io.BytesIO(); wb.save(data); data.seek(0)
        media, fn = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{base}.xlsx"
    data.seek(0)
    return StreamingResponse(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{fn.encode("ascii","ignore").decode() or "reporte"}"'})


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="static")
