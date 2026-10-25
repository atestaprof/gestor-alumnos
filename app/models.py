"""Esquema relacional.

Grupo 1─* Alumno
Grupo 1─1 CriterioEvaluacion
Grupo 1─* Evaluacion 1─* Calificacion *─1 Alumno
Alumno 1─* Asistencia (única por alumno+fecha)
"""
import enum
from datetime import date
from sqlalchemy import (String, Integer, Float, Date, ForeignKey, UniqueConstraint,
                        CheckConstraint, Enum)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class EstadoAsistencia(str, enum.Enum):
    PRESENTE = "Presente"
    RETARDO = "Retardo"
    FALTA = "Falta"
    JUSTIFICADO = "Justificado"


class TipoEvaluacion(str, enum.Enum):
    TAREA = "Tarea"
    PRACTICA = "Práctica"
    EXAMEN = "Examen"


class Grupo(Base):
    __tablename__ = "grupos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    periodo: Mapped[str] = mapped_column(String(50), default="")
    __table_args__ = (UniqueConstraint("nombre", "periodo"),)

    alumnos = relationship("Alumno", back_populates="grupo", cascade="all, delete-orphan")
    criterio = relationship("CriterioEvaluacion", uselist=False, back_populates="grupo",
                            cascade="all, delete-orphan")
    evaluaciones = relationship("Evaluacion", back_populates="grupo", cascade="all, delete-orphan")


class Alumno(Base):
    __tablename__ = "alumnos"
    id: Mapped[int] = mapped_column(primary_key=True)
    matricula: Mapped[str] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(200))
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id", ondelete="CASCADE"))
    __table_args__ = (UniqueConstraint("grupo_id", "matricula"),)

    grupo = relationship("Grupo", back_populates="alumnos")
    asistencias = relationship("Asistencia", cascade="all, delete-orphan")
    calificaciones = relationship("Calificacion", cascade="all, delete-orphan")


class CriterioEvaluacion(Base):
    __tablename__ = "criterios_evaluacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id", ondelete="CASCADE"), unique=True)
    pct_asistencia: Mapped[float] = mapped_column(Float, default=20)
    pct_tareas: Mapped[float] = mapped_column(Float, default=20)
    pct_practicas: Mapped[float] = mapped_column(Float, default=20)
    pct_examenes: Mapped[float] = mapped_column(Float, default=40)
    __table_args__ = (
        CheckConstraint("ROUND(pct_asistencia + pct_tareas + pct_practicas + pct_examenes, 2) = 100",
                        name="ck_suma_100"),
    )
    grupo = relationship("Grupo", back_populates="criterio")


class Asistencia(Base):
    __tablename__ = "asistencias"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date)
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id", ondelete="CASCADE"))
    estado: Mapped[EstadoAsistencia] = mapped_column(Enum(EstadoAsistencia, values_callable=lambda e: [x.value for x in e]))
    __table_args__ = (UniqueConstraint("alumno_id", "fecha"),)


class Evaluacion(Base):
    __tablename__ = "evaluaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id", ondelete="CASCADE"))
    tipo: Mapped[TipoEvaluacion] = mapped_column(Enum(TipoEvaluacion, values_callable=lambda e: [x.value for x in e]))
    titulo: Mapped[str] = mapped_column(String(200))
    fecha: Mapped[date] = mapped_column(Date)
    max_puntos: Mapped[float] = mapped_column(Float, default=100)
    __table_args__ = (CheckConstraint("max_puntos > 0", name="ck_max_pos"),)

    grupo = relationship("Grupo", back_populates="evaluaciones")
    calificaciones = relationship("Calificacion", cascade="all, delete-orphan")


class Calificacion(Base):
    __tablename__ = "calificaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluacion_id: Mapped[int] = mapped_column(ForeignKey("evaluaciones.id", ondelete="CASCADE"))
    alumno_id: Mapped[int] = mapped_column(ForeignKey("alumnos.id", ondelete="CASCADE"))
    puntaje: Mapped[float] = mapped_column(Float)
    __table_args__ = (UniqueConstraint("evaluacion_id", "alumno_id"),)
