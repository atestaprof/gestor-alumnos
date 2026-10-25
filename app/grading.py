"""Lógica de cálculo (funciones puras, sin BD). Escala 0-100."""
from typing import Iterable, Optional

PESO_ASISTENCIA = {"Presente": 1.0, "Retardo": 0.5, "Falta": 0.0}
# "Justificado" se excluye del denominador (no penaliza ni suma).


class PesosInvalidos(ValueError):
    pass


def validar_pesos(asistencia: float, tareas: float, practicas: float, examenes: float) -> None:
    for v in (asistencia, tareas, practicas, examenes):
        if v < 0 or v > 100:
            raise PesosInvalidos("Cada porcentaje debe estar entre 0 y 100")
    if round(asistencia + tareas + practicas + examenes, 2) != 100:
        raise PesosInvalidos("Los porcentajes deben sumar exactamente 100")


def promedio_asistencia(estados: Iterable[str]) -> Optional[float]:
    vals = [PESO_ASISTENCIA[e] for e in estados if e in PESO_ASISTENCIA]
    return None if not vals else 100 * sum(vals) / len(vals)


def promedio_evaluaciones(items: Iterable[tuple[Optional[float], float]]) -> Optional[float]:
    """items: (puntaje | None, max_puntos). Puntaje faltante cuenta como 0."""
    pct = [((p or 0) / m) * 100 for p, m in items if m > 0]
    return None if not pct else sum(pct) / len(pct)


def calificacion_final(pa: float, pt: float, pp: float, pe: float,
                       prom_asist: Optional[float], prom_tareas: Optional[float],
                       prom_practicas: Optional[float], prom_examenes: Optional[float]) -> float:
    """Final = %A*PromA + %T*PromT + %P*PromP + %E*PromE (rubros sin datos valen 0)."""
    return round((pa / 100) * (prom_asist or 0)
                 + (pt / 100) * (prom_tareas or 0)
                 + (pp / 100) * (prom_practicas or 0)
                 + (pe / 100) * (prom_examenes or 0), 2)
