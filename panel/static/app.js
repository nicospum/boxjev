/* JeVentas: panel para revisar lo que sugiere el sistema.
 * Modo local: habla con panel/servidor.py (/api/...).
 * Modo demo: si no hay servidor, lee datos/*.json y guarda las revisiones en este navegador.
 */
"use strict";

// ---------------------------------------------------------------- vocabulario
const SEG = {
  alta_intencion: { n: "Alta intención", d: "Dice dónde y lo necesita en las próximas semanas.", c: "#1F5E57" },
  lista_para_cotizar: { n: "Lista para cotizar", d: "Dice dónde y qué guarda, para qué o cuándo.", c: "#2F6FA3" },
  exploratoria: { n: "Exploratoria", d: "Da un solo dato: la zona, el precio o el motivo.", c: "#A0782C" },
  informacion_insuficiente: { n: "Faltan datos", d: "Todavía no dijo nada útil para cotizar.", c: "#8C948F" },
  listo_para_reservar: { n: "Quiere reservar", d: "Preguntó cómo reservar o pagar. La toma una persona.", c: "#127A4A" },
  objecion_precio: { n: "Le parece caro", d: "Objetó el precio. La toma una persona, sin prometer descuentos.", c: "#B4532A" },
  pidio_tiempo: { n: "Pidió tiempo", d: "Dijo que lo piensa o que avisa más adelante.", c: "#6D5BA8" },
  desistio: { n: "Desistió", d: "Ya no lo necesita o eligió otra opción. No insistir.", c: "#5B6360" },
  no_es_prospecto: { n: "No es prospecto", d: "Cliente actual, búsqueda laboral, proveedor o spam.", c: "#A3A8A5" },
  revision_humana: { n: "Para revisar", d: "Las señales no alcanzan para decidir.", c: "#C77D12" },
};
const ORDEN_SEG = Object.keys(SEG);
const NECESIDAD = {
  mudanza: "Mudanza", reforma: "Obra o reforma", viaje_o_relocalizacion: "Viaje o se va un tiempo",
  stock_empresa: "Stock o equipos de empresa", documentos_archivo: "Documentos", espacio_extra: "Espacio extra en casa",
  sucesion_o_separacion: "Sucesión o separación", otra: "Otro motivo",
};
const SEDE = {
  nunez: "Núñez", palermo: "Palermo", saavedra: "Saavedra", villa_urquiza: "Villa Urquiza", agronomia: "Agronomía",
  almagro: "Almagro", tigre: "Tigre", quilmes_bernal: "Quilmes / Bernal", cordoba: "Córdoba", fuera_de_cobertura: "Fuera de cobertura",
};
const PUNTO = {
  primer_contacto: "Primer mensaje",
  cierre_ventana: "Pasaron 24 h sin respuesta",
  reactivacion: "Volvió a escribir",
};
const ACCION = {
  borrador_libre: "Responder con este mensaje",
  plantilla: "Enviar esta plantilla",
  sin_plantilla: "No enviar plantilla",
  esperar: "Esperar la respuesta",
  seguimiento_libre_antes_de_cierre: "Último mensaje antes de que cierre la ventana",
  atencion_humana_prioritaria: "Atender ahora",
  derivar: "Derivar",
  cerrar_sin_mensaje: "Cerrar sin escribir",
};
const COMPARTIMENTOS = [
  ["menciona_ubicacion", "Zona"],
  ["describe_que_guarda", "Qué guarda"],
  ["dice_cuando", "Cuándo"],
  ["dice_motivo", "Para qué"],
];
const OTRAS_SENALES = {
  pide_precio: "Pide precio", es_empresa: "Es para una empresa", quiere_visitar: "Quiere visitar",
  quiere_reservar: "Quiere reservar", objecion_precio: "Le parece caro", pidio_tiempo: "Pidió tiempo",
  desistio: "Desistió", pregunta_sin_responder: "Tiene una pregunta sin responder",
};
const RESULTADO = { alquilo: "Alquiló", no_alquilo: "No alquiló", desconocido: "Sin dato" };

// ---------------------------------------------------------------- estado
const E = {
  modo: "local", corridas: [], corrida: null, datos: null,
  porId: new Map(), recsPorId: new Map(), lista: [],
  filtro: null, texto: "", soloPendientes: false,
  idSel: null, claveSel: null, verTodas: false,
};
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (p) => `${Math.round(p * 100)}%`;
const fFecha = new Intl.DateTimeFormat("es-AR", { weekday: "short", day: "numeric", month: "short" });
const fHora = new Intl.DateTimeFormat("es-AR", { hour: "2-digit", minute: "2-digit" });
const fCompleta = new Intl.DateTimeFormat("es-AR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const fecha = (iso) => new Date(iso);

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("visible");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove("visible"), 1800);
}

// ---------------------------------------------------------------- datos
async function pedir(url, opts) {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Error ${r.status}`);
  return j;
}

async function detectarModo() {
  try {
    E.corridas = await pedir("api/corridas");
    E.modo = "local";
  } catch {
    E.modo = "demo";
    E.corridas = await pedir("datos/corridas.json");
  }
}

const claveDemo = () => `jeventas.revisiones.${E.corrida}`;
function revisionesDemo() {
  try { return JSON.parse(localStorage.getItem(claveDemo()) || "{}"); } catch { return {}; }
}

async function cargarCorrida(nombre) {
  E.corrida = nombre;
  const d = E.modo === "local"
    ? await pedir(`api/corrida?nombre=${encodeURIComponent(nombre)}`)
    : await pedir(`datos/${encodeURIComponent(nombre)}.json`);
  if (E.modo === "demo") {
    d.recomendaciones.forEach((r) => { r.clave = `${r.id_consulta}|${r.punto}|${r.evaluado_en}`; });
    d.revisiones = revisionesDemo();
  }
  E.datos = d;
  E.porId = new Map(d.consultas.map((c) => [c.id_consulta, c]));
  E.recsPorId = new Map();
  for (const r of d.recomendaciones) {
    if (!E.recsPorId.has(r.id_consulta)) E.recsPorId.set(r.id_consulta, []);
    E.recsPorId.get(r.id_consulta).push(r);
  }
  for (const rs of E.recsPorId.values()) rs.sort((a, b) => a.evaluado_en.localeCompare(b.evaluado_en));
  E.filtro = null; E.idSel = null; E.claveSel = null;
  pintarAviso();
  pintarFiltros();
  pintarLista();
  const primero = E.lista[0];
  if (primero) seleccionar(primero.id);
  else { $("#chatCab").innerHTML = ""; $("#chatCuerpo").innerHTML = ""; $("#lectura").innerHTML = `<p class="lectura-vacia">Este lote no tiene consultas.</p>`; }
  if (!$("#vista-resumen").hidden) pintarResumen();
}

async function guardarRevision(clave, revision) {
  if (E.modo === "local") {
    await pedir("api/revision", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corrida: E.corrida, clave, revision }),
    });
  } else {
    const rev = revisionesDemo();
    if (revision) rev[clave] = { ...revision, fecha: new Date().toISOString() }; else delete rev[clave];
    localStorage.setItem(claveDemo(), JSON.stringify(rev));
  }
  if (revision) E.datos.revisiones[clave] = revision; else delete E.datos.revisiones[clave];
}

// ---------------------------------------------------------------- cabecera
function descCorrida(c) {
  const m = c.meta || {};
  const jev = m.jev === "simulado" ? "Jev simulado" : `Jev real (${m.jev || "?"})`;
  const datos = m.sinteticas ? "consultas inventadas" : "consultas";
  return `${c.nombre}: ${m.consultas ?? "?"} ${datos}, ${jev}`;
}

function pintarCorridas() {
  const sel = $("#selCorrida");
  sel.innerHTML = E.corridas.map((c) => `<option value="${esc(c.nombre)}">${esc(descCorrida(c))}</option>`).join("");
  sel.value = E.corrida || (E.corridas[0] && E.corridas[0].nombre) || "";
}

function pintarAviso() {
  const m = E.datos.meta || {};
  const partes = [];
  if (m.sinteticas) partes.push("las conversaciones son inventadas");
  if (m.jev === "simulado") partes.push("Jev está simulado (sus probabilidades no significan nada)");
  if (m.plantillas_simuladas) partes.push("las plantillas son ejemplos, no están aprobadas");
  let txt = partes.length ? `En este lote ${partes.join(", ")}. Sirve para ver cómo funciona, no para medir calidad.` : "";
  if (E.modo === "demo") txt += " Versión de demostración: tus revisiones quedan guardadas solo en este navegador.";
  const a = $("#aviso");
  a.textContent = txt.trim();
  a.hidden = !txt.trim();
}

// ---------------------------------------------------------------- lista
function segInicial(id) {
  const r = (E.recsPorId.get(id) || [])[0];
  return r ? r.clasificacion.segmento : null;
}
function revisadasDe(id) {
  return (E.recsPorId.get(id) || []).filter((r) => E.datos.revisiones[r.clave]).length;
}

function pintarFiltros() {
  const cuenta = {};
  for (const id of E.recsPorId.keys()) { const s = segInicial(id); cuenta[s] = (cuenta[s] || 0) + 1; }
  const chips = [`<button class="chip-filtro" data-seg="" aria-pressed="${!E.filtro}">Todas <span class="n">${E.recsPorId.size}</span></button>`];
  for (const s of ORDEN_SEG) {
    if (!cuenta[s]) continue;
    chips.push(`<button class="chip-filtro" data-seg="${s}" aria-pressed="${E.filtro === s}"><span class="punto" style="background:${SEG[s].c}"></span>${SEG[s].n} <span class="n">${cuenta[s]}</span></button>`);
  }
  $("#filtrosSeg").innerHTML = chips.join("");
}

function textoConsulta(id) {
  const c = E.porId.get(id);
  return c ? c.mensajes.filter((m) => m.autor === "cliente").map((m) => m.texto).join(" ") : "";
}

function pintarLista() {
  const q = E.texto.trim().toLowerCase();
  E.lista = [...E.recsPorId.keys()]
    .filter((id) => !E.filtro || segInicial(id) === E.filtro)
    .filter((id) => !q || textoConsulta(id).toLowerCase().includes(q) || id.toLowerCase().includes(q))
    .filter((id) => !E.soloPendientes || revisadasDe(id) < E.recsPorId.get(id).length)
    .map((id) => ({ id }));
  $("#contador").textContent = `${E.lista.length} ${E.lista.length === 1 ? "consulta" : "consultas"}`;
  $("#items").innerHTML = E.lista.map(({ id }) => {
    const recs = E.recsPorId.get(id);
    const s = segInicial(id);
    const c = E.porId.get(id);
    const primer = c ? (c.mensajes.find((m) => m.autor === "cliente") || {}).texto : recs[0].clasificacion.explicacion[0];
    const cuando = c ? fCompleta.format(fecha(c.mensajes[0].ts)) : "";
    const rev = revisadasDe(id);
    const res = c && c.resultado ? c.resultado.estado : "desconocido";
    return `<li class="item${id === E.idSel ? " activo" : ""}" data-id="${esc(id)}" tabindex="0">
      <span class="item-banda" style="background:${SEG[s]?.c || "#ccc"}"></span>
      <div>
        <div class="item-sup"><span class="item-seg">${esc(SEG[s]?.n || s)}</span><span>${esc(cuando)}</span></div>
        <div class="item-texto">${esc(primer || "")}</div>
        <div class="item-inf">
          <span>${recs.length} ${recs.length === 1 ? "sugerencia" : "sugerencias"}</span>
          ${rev ? `<span class="revisado">${rev === recs.length ? "Revisada" : `${rev} revisada${rev > 1 ? "s" : ""}`}</span>` : ""}
          ${res === "alquilo" ? `<span class="resultado-alquilo">Alquiló</span>` : ""}
        </div>
      </div></li>`;
  }).join("");
}

// ---------------------------------------------------------------- chat
function seleccionar(id, clave) {
  E.idSel = id;
  const recs = E.recsPorId.get(id) || [];
  E.claveSel = clave || (recs[0] && recs[0].clave);
  document.querySelectorAll(".item").forEach((li) => li.classList.toggle("activo", li.dataset.id === id));
  pintarChat();
  pintarLectura();
}

function pintarChat() {
  const id = E.idSel;
  const c = E.porId.get(id);
  const recs = E.recsPorId.get(id) || [];
  const sel = recs.find((r) => r.clave === E.claveSel);
  const res = c?.resultado?.estado || "desconocido";
  $("#chatCab").innerHTML = `<h2>Consulta ${esc(id)}</h2>
    ${c?.origen?.campania ? `<span class="dato">Campaña: ${esc(c.origen.campania)}</span>` : ""}
    ${c?.propiedades?.zona_formulario ? `<span class="dato">Zona del formulario: ${esc(c.propiedades.zona_formulario)}</span>` : ""}
    <span class="dato">Resultado: ${RESULTADO[res] || res}</span>`;

  if (!c) {
    $("#chatCuerpo").innerHTML = `<p class="futuro-nota">La conversación completa no está disponible en este lote.</p>`;
    return;
  }
  const corte = sel ? fecha(sel.evaluado_en) : null;
  const eventos = [
    ...c.mensajes.map((m) => ({ t: fecha(m.ts), m })),
    ...recs.map((r) => ({ t: fecha(r.evaluado_en), r, orden: 1 })),
  ].sort((a, b) => a.t - b.t || (a.orden || 0) - (b.orden || 0));

  let html = "", dia = "", notaFuturo = false;
  for (const ev of eventos) {
    const d = fFecha.format(ev.t);
    if (d !== dia) { html += `<div class="dia">${esc(d)}</div>`; dia = d; }
    if (ev.r) {
      const r = ev.r, s = r.clasificacion.segmento;
      html += `<button class="marca-decision${r.clave === E.claveSel ? " activa" : ""}" data-clave="${esc(r.clave)}">
        <span><i style="background:${SEG[s]?.c}"></i>${esc(PUNTO[r.punto] || r.punto)}: ${esc(SEG[s]?.n || s)}</span></button>`;
      continue;
    }
    const m = ev.m;
    const futuro = corte && ev.t > corte;
    if (futuro && !notaFuturo) { html += `<p class="futuro-nota">Lo que pasó después. El sistema todavía no lo veía.</p>`; notaFuturo = true; }
    const clases = ["msj", m.autor, m.tipo === "plantilla" ? "plantilla" : "", futuro ? "futuro" : ""].join(" ");
    const tag = m.tipo === "plantilla" ? `<span class="msj-tag">Plantilla ${esc(m.plantilla_id || "")}</span>\n` : "";
    const texto = m.texto || `[${m.tipo}]`;
    html += `<div class="${clases}">${tag}${esc(texto)}<span class="msj-hora">${fHora.format(ev.t)}</span></div>`;
  }
  const cuerpo = $("#chatCuerpo");
  cuerpo.innerHTML = html;
  // Dejar la sugerencia elegida en el tercio inferior: arriba se ve lo que el sistema leyó.
  const activa = cuerpo.querySelector(".marca-decision.activa");
  if (activa) cuerpo.scrollTop = Math.max(0, activa.offsetTop - cuerpo.offsetTop - cuerpo.clientHeight * 0.62);
}

// ---------------------------------------------------------------- lectura del sistema
function valorCompartimento(k, cl, sen) {
  if (k === "menciona_ubicacion") return cl.sede ? SEDE[cl.sede] || cl.sede : "";
  if (k === "dice_motivo") return cl.necesidad ? NECESIDAD[cl.necesidad] || cl.necesidad : "";
  if (k === "dice_cuando") {
    const u = sen.urgencia || {};
    const p = u.p_pronto ?? null;
    const sc = u.score ?? 0;
    if (p !== null ? p >= 0.7 && sc >= 2.5 : sc >= 2.5) return "Esta semana";
    if (p !== null ? p >= 0.7 : sc >= 1.75) return "En 2 o 3 semanas";
    return "Más adelante";
  }
  if (k === "describe_que_guarda") return "Lo describe";
  return "";
}

function pintarLectura() {
  const recs = E.recsPorId.get(E.idSel) || [];
  const r = recs.find((x) => x.clave === E.claveSel);
  const L = $("#lectura");
  if (!r) { L.innerHTML = `<p class="lectura-vacia">Elegí una consulta de la lista.</p>`; return; }
  const cl = r.clasificacion, sen = cl.senales || {}, s = cl.segmento, v = r.ventana, ac = r.accion;
  // En el primer mensaje, que haya una pregunta sin responder es obvio: no se muestra (lotes viejos).
  const alertas = r.punto === "primer_contacto" ? cl.alertas.filter((a) => !a.includes("pregunta")) : cl.alertas;
  const senalOculta = r.punto === "primer_contacto" ? "pregunta_sin_responder" : null;

  const ventana = v.abierta
    ? `<span class="ventana"><i></i>Ventana abierta: quedan ${Math.max(0, Math.round(v.horas_restantes))} h para escribir libremente</span>`
    : `<span class="ventana cerrada"><i></i>Ventana cerrada: solo se puede enviar una plantilla aprobada</span>`;

  const chips = [
    cl.necesidad ? NECESIDAD[cl.necesidad] : null,
    cl.sede ? `Sede ${SEDE[cl.sede] || cl.sede}` : null,
    cl.es_empresa === "si" ? "Empresa" : null,
  ].filter(Boolean).map((t) => `<span class="dato-chip">${esc(t)}</span>`).join("");

  const comps = COMPARTIMENTOS.map(([k, nombre]) => {
    const x = sen[k] || { prob: 0, lectura: "no" };
    const val = x.lectura === "si" ? valorCompartimento(k, cl, sen) : x.lectura === "duda" ? "No está claro" : "No lo dijo";
    return `<div class="comp ${x.lectura}"><span class="comp-nombre">${nombre}</span><span class="comp-valor">${esc(val)}</span>
      <span class="comp-prob">${pct(x.prob)}</span></div>`;
  }).join("");

  const otras = Object.entries(OTRAS_SENALES)
    .map(([k, n]) => [k, n, sen[k]]).filter(([k, , x]) => x && k !== senalOculta)
    .sort((a, b) => b[2].prob - a[2].prob);
  const visibles = E.verTodas ? otras : otras.filter(([, , x]) => x.prob >= 0.3);
  const senalesHtml = visibles.map(([, n, x]) => `<li class="senal ${x.lectura}"><span>${esc(n)}</span>
      <span class="barra-p"><i style="width:${pct(x.prob)}"></i></span><span class="senal-p">${pct(x.prob)}</span></li>`).join("")
    || `<li class="senal"><span style="color:var(--acero)">Ninguna otra señal fuerte.</span></li>`;

  let sug;
  if (ac.tipo === "borrador_libre") {
    const b = ac.borrador || {};
    sug = `<div class="sugerencia"><div class="sug-accion">${ACCION[ac.tipo]}</div><div class="sug-texto">${esc(b.texto)}</div>
      <div class="sug-pie"><button class="boton chico" data-copiar="${esc(b.texto)}">Copiar</button>
      <span>Borrador: lo revisa y lo envía una persona.</span>
      ${(b.riesgos || []).map((x) => `<span class="etiqueta-mini">Revisar: ${esc(x)}</span>`).join("")}</div></div>`;
  } else if (ac.tipo === "plantilla") {
    const p = ac.plantilla;
    sug = `<div class="sugerencia plantilla"><div class="sug-accion">${ACCION[ac.tipo]}: ${esc(p.nombre_meta)}</div><div class="sug-texto">${esc(p.texto)}</div>
      <div class="sug-pie"><span>${esc(ac.motivo || "")}</span>${ac.simulada ? `<span class="etiqueta-mini">Ejemplo, no aprobada</span>` : ""}</div></div>`;
  } else {
    sug = `<div class="sugerencia neutra"><div class="sug-accion">${ACCION[ac.tipo] || ac.tipo}</div>
      <div class="sug-texto">${esc(ac.detalle || ac.motivo || "")}</div></div>`;
  }

  const o = r.observado || {};
  const obs = `<dl class="observado">
    <dt>Ventas respondió</dt><dd>${o.siguiente_mensaje_ventas ? esc(o.siguiente_mensaje_ventas) + (o.horas_hasta_respuesta_ventas != null ? ` <span style="color:var(--acero)">(a las ${horas(o.horas_hasta_respuesta_ventas)})</span>` : "") : "No hay otro mensaje de Ventas"}</dd>
    ${o.plantilla_usada_por_ventas ? `<dt>Plantilla usada</dt><dd>${esc(o.plantilla_usada_por_ventas)}</dd>` : ""}
    <dt>El cliente</dt><dd>${o.prospecto_volvio_a_escribir ? "Volvió a escribir" : "No volvió a escribir"}</dd>
    <dt>Resultado</dt><dd>${RESULTADO[o.resultado] || "Sin dato"}</dd></dl>`;

  const et = r.etiqueta_ventas;
  const etHtml = et && et.segmento
    ? `<p class="pregunta" style="color:var(--acero);font-size:13px">Clasificación cargada por Ventas en el lote: <b style="color:var(--tinta)">${esc(SEG[et.segmento]?.n || et.segmento)}</b>${et.revisado_por === "simulado" ? " (simulada)" : ""}</p>` : "";

  L.innerHTML = `
    <div class="momento"><b>${esc(PUNTO[r.punto] || r.punto)}</b><span>${esc(fCompleta.format(fecha(r.evaluado_en)))}</span></div>
    ${ventana}
    <div class="etiqueta" style="--seg:${SEG[s]?.c || "#999"}">
      <div class="etiqueta-nombre">${esc(SEG[s]?.n || s)}</div>
      <div class="etiqueta-desc">${esc(SEG[s]?.d || "")}</div>
      ${chips ? `<div class="etiqueta-datos">${chips}</div>` : ""}
      ${cl.revision_humana && s !== "no_es_prospecto" ? `<div class="revision-flag">Necesita una persona${cl.motivo_revision ? `: ${esc(cl.motivo_revision)}` : ""}</div>` : ""}
    </div>

    <div class="bloque"><h3>Para cotizar hace falta<small>lo que ya dijo el cliente</small></h3><div class="compartimentos">${comps}</div></div>

    <div class="bloque"><h3>Por qué</h3><ul class="porque">${cl.explicacion.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      ${alertas.length ? `<div class="alertas">${alertas.map((x) => `<div class="alerta">${esc(x)}</div>`).join("")}</div>` : ""}</div>

    <div class="bloque"><h3>Otras señales</h3><ul class="senales">${senalesHtml}</ul>
      ${otras.length > visibles.length || E.verTodas ? `<button class="ver-mas" data-ver-todas>${E.verTodas ? "Ver solo las fuertes" : `Ver todas (${otras.length})`}</button>` : ""}</div>

    <div class="bloque"><h3>Qué sugiere</h3>${sug}</div>

    <div class="bloque"><h3>Qué pasó en realidad</h3>${obs}</div>

    <div class="bloque revision" id="revision">${formRevision(r)}${etHtml}</div>`;
}

function horas(h) {
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} días`;
}

function formRevision(r) {
  const v = E.datos.revisiones[r.clave] || {};
  const opciones = ORDEN_SEG.map((k) => `<option value="${k}"${v.segmento_correcto === k ? " selected" : ""}>${SEG[k].n}</option>`).join("");
  const nota = (n) => `<button data-nota="${n}" aria-pressed="${v.sugerencia_nota === n}">${n}</button>`;
  return `<h3>Tu revisión</h3>
    <p class="pregunta">¿La clasificación es correcta?</p>
    <div class="segmentado" role="group">
      <button data-ok="si" aria-pressed="${v.segmento_ok === "si"}">Sí</button>
      <button data-ok="no" aria-pressed="${v.segmento_ok === "no"}">No</button>
    </div>
    <div class="fila" ${v.segmento_ok === "no" ? "" : "hidden"} id="filaCorrecto">
      <p class="pregunta">¿Cuál era?</p>
      <select id="segCorrecto"><option value="">Elegir</option>${opciones}</select>
    </div>
    <div class="fila">
      <p class="pregunta">¿Sirve lo que sugiere?</p>
      <div class="escala" role="group">${[1, 2, 3, 4, 5].map(nota).join("")}</div>
      <div class="escala-rotulos"><span>No sirve</span><span>Lo enviaría tal cual</span></div>
    </div>
    <div class="fila">
      <p class="pregunta">Comentario</p>
      <textarea id="comentario" placeholder="Qué cambiarías">${esc(v.comentario || "")}</textarea>
    </div>
    <div class="guardado" id="guardado">${v.fecha ? "Guardada" : ""}</div>`;
}

async function actualizarRevision(cambio) {
  const r = (E.recsPorId.get(E.idSel) || []).find((x) => x.clave === E.claveSel);
  if (!r) return;
  const prev = E.datos.revisiones[r.clave] || { segmento_ok: null, segmento_correcto: null, sugerencia_nota: null, comentario: "" };
  const nueva = { ...prev, ...cambio };
  if (nueva.segmento_ok !== "no") nueva.segmento_correcto = null;
  const vacia = !nueva.segmento_ok && !nueva.sugerencia_nota && !nueva.comentario;
  try {
    await guardarRevision(r.clave, vacia ? null : nueva);
    $("#guardado").textContent = vacia ? "" : "Guardada";
    $("#revision").querySelectorAll("[data-ok]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.ok === nueva.segmento_ok)));
    $("#revision").querySelectorAll("[data-nota]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.nota) === nueva.sugerencia_nota)));
    $("#filaCorrecto").hidden = nueva.segmento_ok !== "no";
    actualizarItem(E.idSel);
  } catch (e) {
    $("#guardado").textContent = `No se pudo guardar: ${e.message}`;
  }
}

function actualizarItem(id) {
  const li = document.querySelector(`.item[data-id="${CSS.escape(id)}"] .item-inf`);
  if (!li) return;
  const recs = E.recsPorId.get(id), rev = revisadasDe(id);
  const c = E.porId.get(id);
  li.innerHTML = `<span>${recs.length} ${recs.length === 1 ? "sugerencia" : "sugerencias"}</span>
    ${rev ? `<span class="revisado">${rev === recs.length ? "Revisada" : `${rev} revisada${rev > 1 ? "s" : ""}`}</span>` : ""}
    ${c?.resultado?.estado === "alquilo" ? `<span class="resultado-alquilo">Alquiló</span>` : ""}`;
}

// ---------------------------------------------------------------- resumen
function pintarResumen() {
  const d = E.datos;
  const recs = d.recomendaciones;
  const primeros = recs.filter((r) => r.punto === "primer_contacto");
  const conEt = primeros.filter((r) => r.etiqueta_ventas && r.etiqueta_ventas.segmento);
  const decididos = conEt.filter((r) => !r.clasificacion.revision_humana || r.clasificacion.segmento === "no_es_prospecto");
  const aciertos = decididos.filter((r) => r.clasificacion.segmento === r.etiqueta_ventas.segmento).length;
  const revs = Object.values(d.revisiones);
  const revSeg = revs.filter((v) => v.segmento_ok);
  const revOk = revSeg.filter((v) => v.segmento_ok === "si").length;
  const notas = revs.map((v) => v.sugerencia_nota).filter(Boolean);
  const notaProm = notas.length ? (notas.reduce((a, b) => a + b, 0) / notas.length).toFixed(1).replace(".", ",") : "–";
  const m = d.meta || {};

  const titulo = conEt.length
    ? `El sistema coincidió con Ventas en ${aciertos} de ${decididos.length} primeros mensajes`
    : `${primeros.length} consultas analizadas`;

  // distribución por segmento (primer mensaje)
  const cuenta = {};
  primeros.forEach((r) => { cuenta[r.clasificacion.segmento] = (cuenta[r.clasificacion.segmento] || 0) + 1; });
  const max = Math.max(1, ...Object.values(cuenta));
  const distr = ORDEN_SEG.filter((s) => cuenta[s]).map((s) => `<div class="barra-fila"><span>${SEG[s].n}</span>
    <span class="pista"><i style="width:${(100 * cuenta[s]) / max}%;background:${SEG[s].c}"></i></span><span class="num">${cuenta[s]}</span></div>`).join("");

  // acciones
  const acc = {};
  recs.forEach((r) => { acc[r.accion.tipo] = (acc[r.accion.tipo] || 0) + 1; });
  const maxA = Math.max(1, ...Object.values(acc));
  const acciones = Object.entries(acc).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<div class="barra-fila"><span>${ACCION[k] || k}</span>
    <span class="pista"><i style="width:${(100 * n) / maxA}%;background:var(--petroleo)"></i></span><span class="num">${n}</span></div>`).join("");

  // resultado por segmento
  const resSeg = {};
  primeros.forEach((r) => {
    const s = r.clasificacion.segmento, o = (r.observado || {}).resultado || "desconocido";
    resSeg[s] = resSeg[s] || { alquilo: 0, no_alquilo: 0, desconocido: 0 };
    resSeg[s][o] = (resSeg[s][o] || 0) + 1;
  });
  const COL = { alquilo: "#127A4A", no_alquilo: "#B9C1BC", desconocido: "#E3E7E4" };
  const resultados = ORDEN_SEG.filter((s) => resSeg[s]).map((s) => {
    const x = resSeg[s], tot = x.alquilo + x.no_alquilo + x.desconocido;
    return `<div class="barra-fila"><span>${SEG[s].n}</span><span class="pista">
      ${["alquilo", "no_alquilo", "desconocido"].map((k) => `<i style="width:${(100 * x[k]) / tot}%;background:${COL[k]}" title="${RESULTADO[k]}: ${x[k]}"></i>`).join("")}
      </span><span class="num">${pct(x.alquilo / tot)}</span></div>`;
  }).join("");

  // matriz
  let matriz = "";
  if (conEt.length) {
    const segs = ORDEN_SEG.filter((s) => conEt.some((r) => r.etiqueta_ventas.segmento === s || r.clasificacion.segmento === s));
    const celda = {};
    conEt.forEach((r) => { const k = `${r.etiqueta_ventas.segmento}|${r.clasificacion.segmento}`; celda[k] = (celda[k] || 0) + 1; });
    const maxC = Math.max(1, ...Object.values(celda));
    matriz = `<div class="panel ancho"><h2>Dónde coincide y dónde no</h2>
      <p class="nota">Cada fila es lo que dijo Ventas; cada columna, lo que dijo el sistema. La diagonal son los aciertos.</p>
      <div style="overflow-x:auto"><table class="matriz"><thead><tr><th></th>${segs.map((s) => `<th>${SEG[s].n}</th>`).join("")}</tr></thead><tbody>
      ${segs.map((f) => `<tr><th class="fila">${SEG[f].n}</th>${segs.map((c) => {
        const n = celda[`${f}|${c}`] || 0, a = n / maxC;
        const diag = f === c;
        const bg = n ? (diag ? `rgba(31,94,87,${0.12 + a * 0.75})` : `rgba(180,83,42,${0.12 + a * 0.6})`) : "#F6F7F6";
        return `<td class="${diag ? "diag" : ""}" style="background:${bg};color:${a > 0.5 ? "#fff" : "inherit"}">${n || ""}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table></div></div>`;
  }

  $("#vista-resumen").innerHTML = `<div class="resumen">
    <h1>${esc(titulo)}</h1>
    <p class="bajada">${m.sinteticas ? "Las conversaciones de este lote son inventadas y la clasificación de Ventas está simulada. " : ""}${m.jev === "simulado" ? "Jev está simulado: estos números solo muestran cómo se van a leer los resultados. " : ""}El acuerdo se mide sobre el primer mensaje de cada consulta; los casos que el sistema mandó a revisar no cuentan como aciertos ni como errores.</p>
    <div class="cifras">
      <div class="cifra"><b>${conEt.length ? pct(aciertos / Math.max(1, decididos.length)) : "–"}</b><span>Coincide con Ventas</span></div>
      <div class="cifra"><b>${primeros.filter((r) => r.clasificacion.revision_humana).length}</b><span>Mandó a revisar a una persona</span></div>
      <div class="cifra"><b>${revs.length} <span style="font-size:15px;color:var(--acero)">de ${recs.length}</span></b><span>Sugerencias revisadas por vos</span></div>
      <div class="cifra"><b>${revSeg.length ? pct(revOk / revSeg.length) : "–"}</b><span>Correctas según tus revisiones${notas.length ? `, nota media ${notaProm}` : ""}</span></div>
    </div>
    <div class="grilla">
      <div class="panel"><h2>Cómo clasificó el primer mensaje</h2><p class="nota">${primeros.length} consultas</p><div class="barras">${distr}</div></div>
      <div class="panel"><h2>Qué sugirió hacer</h2><p class="nota">${recs.length} momentos en que había que decidir algo</p><div class="barras">${acciones}</div></div>
      ${matriz}
      <div class="panel ancho"><h2>Cuántos terminaron alquilando, según cómo empezaron</h2>
        <p class="nota">Sirve para ver si las categorías separan bien. No prueba que el sistema cause ventas.</p>
        <div class="leyenda"><span style="--c:${COL.alquilo}">Alquiló</span><span style="--c:${COL.no_alquilo}">No alquiló</span><span style="--c:#D5DAD6">Sin dato</span></div>
        <div class="barras">${resultados}</div></div>
    </div>
    <div class="resumen-acciones">${E.modo === "local" ? `<a class="boton" href="api/revisiones.csv?nombre=${encodeURIComponent(E.corrida)}">Descargar tus revisiones (CSV)</a>` : `<button class="boton" id="btnCsvDemo">Descargar tus revisiones (CSV)</button>`}</div>
  </div>`;
}

function descargarCsvDemo() {
  const filas = [["id_consulta", "momento", "evaluado_en", "segmento_sistema", "segmento_ok", "segmento_correcto", "accion", "nota_sugerencia", "comentario"]];
  for (const r of E.datos.recomendaciones) {
    const v = E.datos.revisiones[r.clave];
    if (v) filas.push([r.id_consulta, r.punto, r.evaluado_en, r.clasificacion.segmento, v.segmento_ok || "", v.segmento_correcto || "", r.accion.tipo, v.sugerencia_nota || "", v.comentario || ""]);
  }
  const csv = "﻿" + filas.map((f) => f.map((x) => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `revisiones_${E.corrida}.csv`;
  a.click();
}

// ---------------------------------------------------------------- importar
const archivosElegidos = [];
function pintarArchivos() {
  $("#zonaLista").innerHTML = archivosElegidos.map((f) => `<li>${esc(f.name)}</li>`).join("");
  $("#btnImportar").disabled = !archivosElegidos.length;
}
function agregarArchivos(lista) {
  for (const f of lista) if (!archivosElegidos.some((x) => x.name === f.name)) archivosElegidos.push(f);
  pintarArchivos();
}

async function importar() {
  const est = $("#importarEstado");
  est.classList.remove("error");
  const jev = document.querySelector("input[name=jev]:checked").value;
  if (jev === "api" && !$("#aprobado").checked) {
    est.textContent = "Para usar Jev real, confirmá que Don Box aprobó compartir estas conversaciones.";
    est.classList.add("error");
    return;
  }
  $("#btnImportar").disabled = true;
  est.textContent = "Leyendo archivos…";
  try {
    const archivos = await Promise.all(archivosElegidos.map(async (f) => ({ nombre: f.name, contenido: await f.text() })));
    est.textContent = "Analizando conversaciones. Puede tardar un poco.";
    const r = await pedir("api/importar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        archivos, jev, aprobado: $("#aprobado").checked, simular_plantillas: $("#simularPlantillas").checked,
        nombres_ventas: $("#nombresVentas").value, etiqueta: $("#etiquetaLote").value,
      }),
    });
    archivosElegidos.length = 0; pintarArchivos();
    est.textContent = `Listo: ${r.consultas} consultas analizadas.`;
    E.corridas = await pedir("api/corridas");
    E.corrida = r.corrida;
    pintarCorridas();
    await cargarCorrida(r.corrida);
    mostrarVista("consultas");
    toast(`Lote ${r.corrida} creado`);
  } catch (e) {
    est.textContent = e.message;
    est.classList.add("error");
  } finally {
    $("#btnImportar").disabled = !archivosElegidos.length;
  }
}

// ---------------------------------------------------------------- vistas y eventos
function mostrarVista(v) {
  for (const n of ["consultas", "resumen", "importar"]) $(`#vista-${n}`).hidden = n !== v;
  document.querySelectorAll(".pestana").forEach((b) => b.classList.toggle("activa", b.dataset.vista === v));
  if (v === "resumen" && E.datos) pintarResumen();
}

function moverSeleccion(delta) {
  const i = E.lista.findIndex((x) => x.id === E.idSel);
  const sig = E.lista[Math.min(E.lista.length - 1, Math.max(0, i + delta))];
  if (sig && sig.id !== E.idSel) {
    seleccionar(sig.id);
    document.querySelector(`.item[data-id="${CSS.escape(sig.id)}"]`)?.scrollIntoView({ block: "nearest" });
  }
}

function eventos() {
  document.querySelectorAll(".pestana").forEach((b) => b.addEventListener("click", () => mostrarVista(b.dataset.vista)));
  $("#selCorrida").addEventListener("change", (e) => cargarCorrida(e.target.value));
  $("#buscar").addEventListener("input", (e) => { E.texto = e.target.value; pintarLista(); });
  $("#soloPendientes").addEventListener("change", (e) => { E.soloPendientes = e.target.checked; pintarLista(); });
  $("#filtrosSeg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-seg]");
    if (!b) return;
    E.filtro = b.dataset.seg || null;
    pintarFiltros(); pintarLista();
    if (E.lista[0] && !E.lista.some((x) => x.id === E.idSel)) seleccionar(E.lista[0].id);
  });
  $("#items").addEventListener("click", (e) => { const li = e.target.closest(".item"); if (li) seleccionar(li.dataset.id); });
  $("#items").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { const li = e.target.closest(".item"); if (li) seleccionar(li.dataset.id); }
  });
  document.addEventListener("keydown", (e) => {
    if ($("#vista-consultas").hidden || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); moverSeleccion(1); }
    if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); moverSeleccion(-1); }
  });
  $("#chatCuerpo").addEventListener("click", (e) => {
    const b = e.target.closest(".marca-decision");
    if (b) { E.claveSel = b.dataset.clave; pintarChat(); pintarLectura(); }
  });
  $("#lectura").addEventListener("click", (e) => {
    const t = e.target;
    if (t.matches("[data-copiar]")) { navigator.clipboard?.writeText(t.dataset.copiar); toast("Mensaje copiado"); }
    if (t.matches("[data-ver-todas]")) { E.verTodas = !E.verTodas; pintarLectura(); }
    if (t.matches("[data-ok]")) actualizarRevision({ segmento_ok: t.getAttribute("aria-pressed") === "true" ? null : t.dataset.ok });
    if (t.matches("[data-nota]")) {
      const n = Number(t.dataset.nota);
      actualizarRevision({ sugerencia_nota: t.getAttribute("aria-pressed") === "true" ? null : n });
    }
  });
  $("#lectura").addEventListener("change", (e) => {
    if (e.target.id === "segCorrecto") actualizarRevision({ segmento_correcto: e.target.value || null });
    if (e.target.id === "comentario") actualizarRevision({ comentario: e.target.value });
  });
  $("#vista-resumen").addEventListener("click", (e) => { if (e.target.id === "btnCsvDemo") descargarCsvDemo(); });

  // importar
  const zona = $("#zona");
  zona.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#archivos").click(); } });
  $("#archivos").addEventListener("change", (e) => { agregarArchivos(e.target.files); e.target.value = ""; });
  ["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("encima"); }));
  ["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove("encima"); }));
  zona.addEventListener("drop", (e) => agregarArchivos(e.dataTransfer.files));
  document.querySelectorAll("input[name=jev]").forEach((r) => r.addEventListener("change", () => {
    $("#aprobadoFila").hidden = document.querySelector("input[name=jev]:checked").value !== "api";
  }));
  $("#btnImportar").addEventListener("click", importar);
}

async function iniciar() {
  eventos();
  try {
    await detectarModo();
  } catch {
    $("#lectura").innerHTML = `<p class="lectura-vacia">No se encontraron lotes. Abrí el panel con <code>python scripts/abrir_panel.py</code>.</p>`;
    return;
  }
  if (E.modo === "demo") {
    $("#vista-importar .importar").innerHTML = `<h1>Importar conversaciones</h1>
      <p class="bajada">Esta es la versión de demostración publicada en internet: no recibe archivos, para que ninguna conversación real quede en un sitio público. Para importar, abrí el panel en tu computadora con <code>python scripts/abrir_panel.py</code>.</p>`;
  }
  if (!E.corridas.length) {
    $("#lectura").innerHTML = `<p class="lectura-vacia">Todavía no hay lotes. Importá conversaciones o corré <code>python scripts/correr_piloto.py</code>.</p>`;
    mostrarVista("importar");
    return;
  }
  E.corrida = E.corridas[0].nombre;
  pintarCorridas();
  await cargarCorrida(E.corrida);
}

iniciar();
