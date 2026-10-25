import pytest
from app import grading as g


def test_pesos_validos():
    g.validar_pesos(20, 20, 20, 40)
    g.validar_pesos(25, 25, 25, 25)
    g.validar_pesos(33.33, 33.33, 0, 33.34)


@pytest.mark.parametrize("p", [(20, 30, 10, 30), (50, 50, 10, 0), (-10, 60, 25, 25), (0, 0, 0, 101), (20, 20, 20, 20)])
def test_pesos_invalidos(p):
    with pytest.raises(g.PesosInvalidos):
        g.validar_pesos(*p)


def test_promedio_asistencia():
    assert g.promedio_asistencia(["Presente", "Falta"]) == 50
    assert g.promedio_asistencia(["Presente", "Retardo"]) == 75
    assert g.promedio_asistencia(["Presente", "Justificado"]) == 100  # justificado no cuenta
    assert g.promedio_asistencia([]) is None


def test_promedio_evaluaciones_y_faltantes():
    assert g.promedio_evaluaciones([(8, 10), (50, 100)]) == 65
    assert g.promedio_evaluaciones([(10, 10), (None, 10)]) == 50  # faltante = 0
    assert g.promedio_evaluaciones([]) is None


def test_final_formula():
    assert g.calificacion_final(20, 20, 20, 40, 100, 80, 90, 70) == 20 + 16 + 18 + 28


def test_final_cambia_con_pesos():
    a = g.calificacion_final(20, 20, 20, 40, 100, 80, 50, 60)
    b = g.calificacion_final(10, 10, 20, 60, 100, 80, 50, 60)
    assert (a, b) == (70.0, 64.0)


def test_rubro_sin_datos_vale_cero():
    assert g.calificacion_final(20, 20, 20, 40, 100, None, None, None) == 20
