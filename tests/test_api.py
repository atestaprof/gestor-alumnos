import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base, get_db


@pytest.fixture
def client():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, autoflush=False)
    def override():
        db = S()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_flujo_completo(client):
    r = client.post("/api/import/confirm", json={"nombre": "Mate", "periodo": "2026-A",
        "alumnos": [{"matricula": "1001", "nombre": "Ana"}, {"matricula": "1002", "nombre": "Beto"}]})
    gid = r.json()["id"]
    a, b = [x["id"] for x in client.get(f"/api/grupos/{gid}/alumnos").json()]
    client.put(f"/api/grupos/{gid}/asistencias", json={"fecha": "2026-03-01", "registros": {a: "Presente", b: "Falta"}})
    client.post(f"/api/grupos/{gid}/evaluaciones", json={"tipo": "Tarea", "titulo": "T1", "fecha": "2026-03-02", "max_puntos": 10, "puntajes": {a: 10, b: 5}})
    client.post(f"/api/grupos/{gid}/evaluaciones", json={"tipo": "Práctica", "titulo": "P1", "fecha": "2026-03-02", "max_puntos": 10, "puntajes": {a: 8, b: 4}})
    client.post(f"/api/grupos/{gid}/evaluaciones", json={"tipo": "Examen", "titulo": "E1", "fecha": "2026-03-03", "max_puntos": 100, "puntajes": {a: 90, b: 60}})
    s = client.get(f"/api/grupos/{gid}/sabana").json()["alumnos"]
    assert s[0]["final"] == 0.2 * 100 + 0.2 * 100 + 0.2 * 80 + 0.4 * 90  # 92
    # Cambiar ponderación
    assert client.put(f"/api/grupos/{gid}/criterios", json={"pct_asistencia": 20, "pct_tareas": 10, "pct_practicas": 10, "pct_examenes": 60}).status_code == 200
    assert client.get(f"/api/grupos/{gid}/sabana").json()["alumnos"][0]["final"] == 20 + 10 + 8 + 54
    assert client.put(f"/api/grupos/{gid}/criterios", json={"pct_asistencia": 10, "pct_tareas": 10, "pct_practicas": 10, "pct_examenes": 10}).status_code == 422
    assert client.get(f"/api/grupos/{gid}/export?formato=xlsx").status_code == 200
    assert "Ana" in client.get(f"/api/grupos/{gid}/export?formato=csv").text


def test_puntaje_fuera_de_rango(client):
    gid = client.post("/api/grupos", json={"nombre": "X"}).json()["id"]
    r = client.post(f"/api/grupos/{gid}/evaluaciones", json={"tipo": "Examen", "titulo": "E", "fecha": "2026-01-01", "max_puntos": 10, "puntajes": {}})
    assert r.status_code == 201


def test_migracion_agrega_practicas(tmp_path, monkeypatch):
    from sqlalchemy import text, inspect
    import app.database as d
    eng = create_engine(f"sqlite:///{tmp_path/'old.db'}")
    with eng.begin() as cx:
        cx.execute(text("CREATE TABLE criterios_evaluacion (id INTEGER PRIMARY KEY, grupo_id INTEGER UNIQUE, pct_asistencia FLOAT, pct_tareas FLOAT, pct_examenes FLOAT)"))
        cx.execute(text("INSERT INTO criterios_evaluacion VALUES (1, 1, 20, 30, 50)"))
    monkeypatch.setattr(d, "engine", eng)
    d.migrate()
    with eng.connect() as cx:
        assert cx.execute(text("SELECT pct_practicas, pct_examenes FROM criterios_evaluacion")).one() == (0, 50)
