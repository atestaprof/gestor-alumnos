const $ = s => document.querySelector(s);
const ESTADOS = ["Presente", "Retardo", "Falta", "Justificado"];
let gid = null, alumnos = [], tab = "importar";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = v => v == null ? "—" : v.toFixed(1);

function msg(text, ok = true) {
  const m = $("#msg"); m.textContent = text;
  m.className = `mb-3 p-2 rounded text-sm ${ok ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`;
  setTimeout(() => m.classList.add("hidden"), 5000);
}
async function api(url, opts = {}) {
  if (opts.body && !(opts.body instanceof FormData)) { opts.headers = { "Content-Type": "application/json" }; opts.body = JSON.stringify(opts.body); }
  const r = await fetch(url, opts);
  if (!r.ok) { let d = r.statusText; try { const j = await r.json(); d = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { } msg(d, false); throw new Error(d); }
  return r.status === 204 ? null : r.json();
}

function showTab(t) {
  tab = t;
  document.querySelectorAll(".panel").forEach(p => p.classList.toggle("hidden", p.id !== t));
  document.querySelectorAll(".tab").forEach(b => b.className = `tab px-4 py-2 ${b.dataset.t === t ? "border-b-2 border-[#800020] text-[#800020] font-semibold bg-[#f8fafc]" : "text-slate-500 hover:text-[#800020] border-b-2 border-transparent"} transition-colors`);
  if (gid && t !== "importar") ({ asistencia: loadAsistencia, notas: loadNotas, sabana: loadSabana })[t]();
}
document.querySelectorAll(".tab").forEach(b => b.onclick = () => showTab(b.dataset.t));

async function loadGrupos(select) {
  const gs = await api("/api/grupos");
  $("#grupoSel").innerHTML = gs.map(g => `<option value="${g.id}">${esc(g.nombre)} ${esc(g.periodo)} (${g.alumnos})</option>`).join("");
  if (select) $("#grupoSel").value = select;
  gid = gs.length ? +$("#grupoSel").value : null;
  if (gid) alumnos = await api(`/api/grupos/${gid}/alumnos`); else alumnos = [];
  showTab(gid ? tab : "importar");
}
$("#grupoSel").onchange = async () => { gid = +$("#grupoSel").value; alumnos = await api(`/api/grupos/${gid}/alumnos`); showTab(tab); };
$("#delGrupo").onclick = async () => {
  if (gid && confirm("¿Eliminar el grupo y todos sus datos?")) { await api(`/api/grupos/${gid}`, { method: "DELETE" }); loadGrupos(); }
};

// ---- Importar ----
let pvRows = [];
$("#btnPreview").onclick = async () => {
  const f = $("#pdfFile").files[0]; if (!f) return msg("Selecciona un PDF", false);
  const fd = new FormData(); fd.append("file", f);
  const r = await api("/api/import/preview", { method: "POST", body: fd });
  pvRows = r.rows;
  $("#pvGrupo").value = r.grupo; $("#pvPeriodo").value = r.periodo;
  $("#pvWarn").innerHTML = r.warnings.map(esc).join("<br>");
  renderPreview(); $("#previewBox").classList.remove("hidden");
};
function renderPreview() {
  $("#pvRows").innerHTML = pvRows.map((r, i) => `<tr class="border-b ${r.warnings.length ? "bg-amber-50" : ""}">
    <td><button data-i="${i}" class="rm text-red-600">✕</button></td>
    <td><input data-i="${i}" data-k="matricula" class="ed border rounded p-1 w-32" value="${esc(r.matricula)}"></td>
    <td><input data-i="${i}" data-k="nombre" class="ed border rounded p-1 w-full" value="${esc(r.nombre)}"></td>
    <td class="text-amber-700">${r.warnings.map(esc).join(", ")}</td></tr>`).join("");
  document.querySelectorAll(".ed").forEach(e => e.oninput = () => pvRows[e.dataset.i][e.dataset.k] = e.value);
  document.querySelectorAll(".rm").forEach(b => b.onclick = () => { pvRows.splice(b.dataset.i, 1); renderPreview(); });
}
$("#btnConfirm").onclick = async () => {
  const nombre = $("#pvGrupo").value.trim(); if (!nombre) return msg("Indica el grupo", false);
  const r = await api("/api/import/confirm", { method: "POST", body: { nombre, periodo: $("#pvPeriodo").value.trim(), alumnos: pvRows.map(({ matricula, nombre }) => ({ matricula, nombre })) } });
  msg(`Importados ${r.alumnos} alumnos`); $("#previewBox").classList.add("hidden"); loadGrupos(r.id);
};

// ---- Asistencia ----
const today = () => new Date().toISOString().slice(0, 10);
$("#asFecha").value = today(); $("#evFecha").value = today();
async function loadAsistencia() {
  const cur = await api(`/api/grupos/${gid}/asistencias?fecha=${$("#asFecha").value}`);
  $("#asRows").innerHTML = alumnos.map(a => `<tr class="border-b"><td class="py-1">${esc(a.nombre)} <span class="text-slate-400">${esc(a.matricula)}</span></td>` +
    ESTADOS.map(e => `<td class="text-center"><input type="radio" name="as${a.id}" value="${e}" ${(cur[a.id] || "") === e ? "checked" : ""}></td>`).join("") + "</tr>").join("");
}
$("#asFecha").onchange = loadAsistencia;
$("#asTodos").onclick = () => document.querySelectorAll('#asRows input[value="Presente"]').forEach(i => i.checked = true);
$("#asSave").onclick = async () => {
  const registros = {};
  alumnos.forEach(a => { const c = document.querySelector(`input[name=as${a.id}]:checked`); if (c) registros[a.id] = c.value; });
  const r = await api(`/api/grupos/${gid}/asistencias`, { method: "PUT", body: { fecha: $("#asFecha").value, registros } });
  msg(`Asistencia guardada (${r.guardados})`);
};

// ---- Notas ----
async function loadNotas() {
  $("#evRows").innerHTML = alumnos.map(a => `<tr class="border-b"><td class="py-1">${esc(a.nombre)}</td><td><input type="number" step="any" min="0" data-a="${a.id}" class="np border rounded p-1 w-24"></td></tr>`).join("");
  const evs = await api(`/api/grupos/${gid}/evaluaciones`);
  $("#evList").innerHTML = evs.map(e => `<li class="border rounded p-2"><b>${esc(e.tipo)}</b> ${esc(e.titulo)} · ${e.fecha} · máx ${e.max_puntos}
    <button data-id="${e.id}" class="edit text-[#800020] ml-2">editar notas</button> <button data-id="${e.id}" class="del text-red-600 ml-2">eliminar</button></li>`).join("") || "<li>Sin evaluaciones</li>";
  document.querySelectorAll(".del").forEach(b => b.onclick = async () => { if (confirm("¿Eliminar evaluación?")) { await api(`/api/evaluaciones/${b.dataset.id}`, { method: "DELETE" }); loadNotas(); } });
  document.querySelectorAll(".edit").forEach(b => b.onclick = () => {
    const e = evs.find(x => x.id == b.dataset.id);
    document.querySelectorAll(".np").forEach(i => i.value = e.puntajes[i.dataset.a] ?? "");
    $("#evTipo").value = e.tipo; $("#evTitulo").value = e.titulo; $("#evFecha").value = e.fecha; $("#evMax").value = e.max_puntos;
    $("#evSave").dataset.edit = e.id; $("#evSave").textContent = "Actualizar notas";
    window.scrollTo(0, 0);
  });
}
$("#evSave").onclick = async () => {
  const puntajes = {};
  document.querySelectorAll(".np").forEach(i => puntajes[i.dataset.a] = i.value === "" ? null : +i.value);
  const editId = $("#evSave").dataset.edit;
  if (editId) await api(`/api/evaluaciones/${editId}/calificaciones`, { method: "PUT", body: { puntajes } });
  else {
    const titulo = $("#evTitulo").value.trim(); if (!titulo) return msg("Falta el título", false);
    await api(`/api/grupos/${gid}/evaluaciones`, { method: "POST", body: { tipo: $("#evTipo").value, titulo, fecha: $("#evFecha").value, max_puntos: +$("#evMax").value, puntajes } });
  }
  delete $("#evSave").dataset.edit; $("#evSave").textContent = "Guardar evaluación"; $("#evTitulo").value = "";
  msg("Guardado"); loadNotas();
};

// ---- Sábana ----
async function loadSabana() {
  const c = await api(`/api/grupos/${gid}/criterios`);
  $("#pA").value = c.pct_asistencia; $("#pT").value = c.pct_tareas; $("#pP").value = c.pct_practicas; $("#pE").value = c.pct_examenes;
  $("#expX").href = `/api/grupos/${gid}/export?formato=xlsx`; $("#expC").href = `/api/grupos/${gid}/export?formato=csv`;
  refreshSabana();
}
async function refreshSabana() {
  const [a, t, p, e] = [$("#pA"), $("#pT"), $("#pP"), $("#pE")].map(i => +i.value || 0);
  const sum = Math.round((a + t + p + e) * 100) / 100;
  $("#pSum").textContent = `Σ = ${sum}`; $("#pSum").className = sum === 100 ? "font-mono text-green-700" : "font-mono text-red-700";
  if (sum !== 100) return;
  const s = await api(`/api/grupos/${gid}/sabana?asistencia=${a}&tareas=${t}&practicas=${p}&examenes=${e}`);
  $("#sbRows").innerHTML = s.alumnos.map(r => `<tr class="border-b"><td>${esc(r.matricula)}</td><td>${esc(r.nombre)}</td><td>${r.presentes}</td><td>${r.retardos}</td><td>${r.faltas}</td><td>${r.justificados}</td>
    <td>${fmt(r.prom_asistencia)}</td><td>${fmt(r.prom_tareas)}</td><td>${fmt(r.prom_practicas)}</td><td>${fmt(r.prom_examenes)}</td><td class="font-bold ${r.final < 60 ? "text-red-600" : ""}">${r.final.toFixed(1)}</td></tr>`).join("");
}
["#pA", "#pT", "#pP", "#pE"].forEach(s => $(s).oninput = refreshSabana);
$("#pSave").onclick = async () => {
  await api(`/api/grupos/${gid}/criterios`, { method: "PUT", body: { pct_asistencia: +$("#pA").value, pct_tareas: +$("#pT").value, pct_practicas: +$("#pP").value, pct_examenes: +$("#pE").value } });
  msg("Ponderación guardada");
};

loadGrupos();
