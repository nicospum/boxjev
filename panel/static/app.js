/* JeVentas: panel para revisar y ordenar lo que clasifica Jev.
 * Modo local: habla con panel/servidor.py (/api/...).
 * Modo demo (Netlify): si no hay servidor, lee datos/*.json, solo lectura; revisiones en el navegador.
 */
"use strict";

// ---------------------------------------------------------------- vocabulario
const SEDE = {
  nunez: "Núñez", palermo: "Palermo", saavedra: "Saavedra", villa_urquiza: "Villa Urquiza", agronomia: "Agronomía",
  almagro: "Almagro", tigre: "Tigre", quilmes_bernal: "Quilmes / Bernal", cordoba: "Córdoba", fuera_de_cobertura: "Fuera de cobertura",
};
const NECESIDAD = {
  mudanza: "Mudanza", reforma: "Obra o reforma", viaje_o_relocalizacion: "Viaje o se va un tiempo",
  stock_empresa: "Stock o equipos de empresa", documentos_archivo: "Documentos", espacio_extra: "Espacio extra en casa",
  sucesion_o_separacion: "Sucesión o separación", otra: "Otro motivo",
};
const PUNTO = { primer_contacto: "Primer mensaje", cierre_ventana: "Pasaron 24 h sin respuesta", reactivacion: "Volvió a escribir" };
const ETAPA_DE = { primer_contacto: "primer_contacto", cierre_ventana: "post_24h", reactivacion: "post_24h" };
const ACCION = {
  borrador_libre: "Responder con este mensaje", plantilla: "Enviar esta plantilla", sin_plantilla: "No enviar plantilla",
  esperar: "Esperar la respuesta", seguimiento_libre_antes_de_cierre: "Último mensaje antes de que cierre la ventana",
  atencion_humana_prioritaria: "Atender ahora", derivar: "Derivar", cerrar_sin_mensaje: "Cerrar sin escribir",
  revisar_categoria: "Elegir la categoría a mano",
};
const ACCION_CAT = { responder: "Responder", plantilla: "Enviar plantilla", persona: "Lo atiende una persona", derivar: "Derivar", no_escribir: "No escribir más" };
// Lotes viejos (antes de las categorías editables): segmento -> categoría equivalente
const LEGADO = { listo_para_reservar: "quiere_reservar" };
const COMPARTIMENTOS = [["menciona_ubicacion", "Zona"], ["describe_que_guarda", "Qué guarda"], ["dice_cuando", "Cuándo"], ["dice_motivo", "Para qué"]];
const OTRAS_SENALES = {
  pide_precio: "Pide precio", es_empresa: "Es para una empresa", quiere_visitar: "Quiere visitar", quiere_reservar: "Quiere reservar",
  objecion_precio: "Le parece caro", pidio_tiempo: "Pidió tiempo", desistio: "Desistió", pregunta_sin_responder: "Tiene una pregunta sin responder",
};
const RESULTADO = { alquilo: "Alquiló", no_alquilo: "No alquiló", desconocido: "Sin dato" };
const SIN = { id: "sin_categoria", nombre: "Sin categoría", descripcion: "Jev no encontró una categoría que encaje, o la que tenía se eliminó.", color: "#C77D12", accion: null };

// ---------------------------------------------------------------- estado
const E = {
  modo: "local", corridas: [], corrida: null, datos: null, cats: null, catPorId: new Map(), ajustes: null,
  porId: new Map(), recsPorId: new Map(), lista: [], filtro: null, texto: "", soloPendientes: false,
  idSel: null, claveSel: null, verTodas: false, vista: "consultas", abiertas: new Set(), chat: [],
};
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (p) => `${Math.round((p || 0) * 100)}%`;
const fFecha = new Intl.DateTimeFormat("es-AR", { weekday: "short", day: "numeric", month: "short" });
const fHora = new Intl.DateTimeFormat("es-AR", { hour: "2-digit", minute: "2-digit" });
const fCompleta = new Intl.DateTimeFormat("es-AR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const fecha = (iso) => new Date(iso);
const local = () => E.modo === "local";

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("visible");
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove("visible"), 2200);
}

async function pedir(url, opts) {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Error ${r.status}`);
  return j;
}
const post = (url, cuerpo) => pedir(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });

// ---------------------------------------------------------------- categorías
function setCats(c) {
  E.cats = c;
  E.catPorId = new Map(c.categorias.map((x) => [x.id, x]));
}
function catInfo(id) {
  return E.catPorId.get(id) || (E.cats?.eliminadas || []).find((x) => x.id === id) && { ...SIN, nombre: `${(E.cats.eliminadas.find((x) => x.id === id)).nombre} (eliminada)` } || SIN;
}
function catActual(r) {
  const a = E.datos?.asignaciones?.[r.clave];
  if (a) return a.categoria;
  const cid = r.clasificacion?.categoria?.id;
  if (cid && E.catPorId.has(cid)) return cid;
  if (!r.clasificacion?.categoria) {
    const s = LEGADO[r.clasificacion.segmento] || r.clasificacion.segmento;
    const c = E.catPorId.get(s);
    if (c && c.etapa === ETAPA_DE[r.punto]) return s;
  }
  return "sin_categoria";
}
const catsDeEtapa = (etapa) => (E.cats?.categorias || []).filter((c) => c.etapa === etapa);

// ---------------------------------------------------------------- datos
async function detectarModo() {
  try {
    E.corridas = await pedir("api/corridas");
    E.modo = "local";
    setCats(await pedir("api/categorias"));
    E.ajustes = await pedir("api/ajustes");
  } catch {
    E.modo = "demo";
    E.corridas = await pedir("datos/corridas.json");
    setCats(await pedir("datos/categorias.json").catch(() => ({ etapas: {}, categorias: [], eliminadas: [] })));
  }
}
const claveDemo = () => `jeventas.revisiones.${E.corrida}`;
function revisionesDemo() { try { return JSON.parse(localStorage.getItem(claveDemo()) || "{}"); } catch { return {}; } }

async function cargarCorrida(nombre, conservar = false) {
  const idPrev = E.idSel, clavePrev = E.claveSel;
  E.corrida = nombre;
  const d = local() ? await pedir(`api/corrida?nombre=${encodeURIComponent(nombre)}`) : await pedir(`datos/${encodeURIComponent(nombre)}.json`);
  if (!local()) {
    d.recomendaciones.forEach((r) => { r.clave = `${r.id_consulta}|${r.punto}|${r.evaluado_en}`; });
    d.revisiones = revisionesDemo();
    d.asignaciones = d.asignaciones || {};
    d.reasignaciones = d.reasignaciones || [];
  }
  E.datos = d;
  E.porId = new Map(d.consultas.map((c) => [c.id_consulta, c]));
  E.recsPorId = new Map();
  for (const r of d.recomendaciones) {
    if (!E.recsPorId.has(r.id_consulta)) E.recsPorId.set(r.id_consulta, []);
    E.recsPorId.get(r.id_consulta).push(r);
  }
  for (const rs of E.recsPorId.values()) rs.sort((a, b) => a.evaluado_en.localeCompare(b.evaluado_en));
  if (!conservar) { E.filtro = null; E.idSel = null; E.claveSel = null; }
  pintarAviso(); pintarFiltros(); pintarLista();
  if (conservar && idPrev && E.recsPorId.has(idPrev)) seleccionar(idPrev, clavePrev);
  else if (E.lista[0]) seleccionar(E.lista[0].id);
  else { $("#chatCab").innerHTML = ""; $("#chatCuerpo").innerHTML = ""; $("#lectura").innerHTML = `<p class="lectura-vacia">Este lote no tiene consultas.</p>`; }
  repintarVista();
}

async function recargarTodo(lote) {
  if (local()) {
    E.corridas = await pedir("api/corridas");
    setCats(await pedir("api/categorias"));
  }
  if (lote) E.corrida = lote;
  pintarCorridas();
  await cargarCorrida(lote || E.corrida, !lote || lote === E.corrida);
}

async function guardarRevision(clave, revision) {
  if (local()) await post("api/revision", { corrida: E.corrida, clave, revision });
  else {
    const rev = revisionesDemo();
    if (revision) rev[clave] = { ...revision, fecha: new Date().toISOString() }; else delete rev[clave];
    localStorage.setItem(claveDemo(), JSON.stringify(rev));
  }
  if (revision) E.datos.revisiones[clave] = revision; else delete E.datos.revisiones[clave];
}

// ---------------------------------------------------------------- cabecera
function descCorrida(c) {
  const m = c.meta || {};
  const jev = m.jev === "simulado" ? "Jev simulado" : `Jev real`;
  const datos = m.sinteticas ? "inventadas" : "reales";
  return `${c.nombre}: ${m.consultas ?? "?"} consultas ${datos}, ${jev}`;
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
  let txt = partes.length ? `En este lote ${partes.join(", ")}.` : "";
  if (!local()) txt += " Versión de demostración: solo lectura, tus revisiones quedan en este navegador.";
  const pend = (E.datos.reasignaciones || []).filter((x) => x.estado === "pendiente").length;
  if (pend) txt += ` Hay ${pend} ${pend === 1 ? "contacto" : "contactos"} esperando que confirmes su nueva categoría (en Categorías).`;
  $("#aviso").textContent = txt.trim();
  $("#aviso").hidden = !txt.trim();
}

// ---------------------------------------------------------------- lista
const recInicial = (id) => (E.recsPorId.get(id) || [])[0];
const revisadasDe = (id) => (E.recsPorId.get(id) || []).filter((r) => E.datos.revisiones[r.clave]).length;

function pintarFiltros() {
  const cuenta = {};
  for (const id of E.recsPorId.keys()) { const s = catActual(recInicial(id)); cuenta[s] = (cuenta[s] || 0) + 1; }
  const chips = [`<button class="chip-filtro" data-seg="" aria-pressed="${!E.filtro}">Todas <span class="n">${E.recsPorId.size}</span></button>`];
  for (const s of [...catsDeEtapa("primer_contacto").map((c) => c.id), "sin_categoria"]) {
    if (!cuenta[s]) continue;
    const c = catInfo(s);
    chips.push(`<button class="chip-filtro" data-seg="${esc(s)}" aria-pressed="${E.filtro === s}"><span class="punto" style="background:${esc(c.color)}"></span>${esc(c.nombre)} <span class="n">${cuenta[s]}</span></button>`);
  }
  $("#filtrosSeg").innerHTML = chips.join("");
}
function textoConsulta(id) {
  const c = E.porId.get(id);
  return c ? c.mensajes.filter((m) => m.autor === "cliente").map((m) => m.texto).join(" ") : "";
}
function itemInf(id) {
  const recs = E.recsPorId.get(id), rev = revisadasDe(id), c = E.porId.get(id);
  return `<span>${recs.length} ${recs.length === 1 ? "sugerencia" : "sugerencias"}</span>
    ${rev ? `<span class="revisado">${rev === recs.length ? "Revisada" : `${rev} revisada${rev > 1 ? "s" : ""}`}</span>` : ""}
    ${c?.resultado?.estado === "alquilo" ? `<span class="resultado-alquilo">Alquiló</span>` : ""}`;
}
function pintarLista() {
  const q = E.texto.trim().toLowerCase();
  E.lista = [...E.recsPorId.keys()]
    .filter((id) => !E.filtro || catActual(recInicial(id)) === E.filtro)
    .filter((id) => !q || textoConsulta(id).toLowerCase().includes(q) || id.toLowerCase().includes(q))
    .filter((id) => !E.soloPendientes || revisadasDe(id) < E.recsPorId.get(id).length)
    .map((id) => ({ id }));
  $("#contador").textContent = `${E.lista.length} ${E.lista.length === 1 ? "consulta" : "consultas"}`;
  $("#items").innerHTML = E.lista.map(({ id }) => {
    const r0 = recInicial(id), cat = catInfo(catActual(r0)), c = E.porId.get(id);
    const primer = c ? (c.mensajes.find((m) => m.autor === "cliente") || {}).texto : "";
    return `<li class="item${id === E.idSel ? " activo" : ""}" data-id="${esc(id)}" tabindex="0">
      <span class="item-banda" style="background:${esc(cat.color)}"></span>
      <div><div class="item-sup"><span class="item-seg">${esc(cat.nombre)}</span><span>${c ? esc(fCompleta.format(fecha(c.mensajes[0].ts))) : ""}</span></div>
        <div class="item-texto">${esc(primer || "")}</div><div class="item-inf">${itemInf(id)}</div></div></li>`;
  }).join("");
}

// ---------------------------------------------------------------- chat de la consulta
function seleccionar(id, clave) {
  E.idSel = id;
  const recs = E.recsPorId.get(id) || [];
  E.claveSel = clave && recs.some((r) => r.clave === clave) ? clave : recs[0]?.clave;
  document.querySelectorAll(".item").forEach((li) => li.classList.toggle("activo", li.dataset.id === id));
  pintarChat(); pintarLectura();
}
function pintarChat() {
  const id = E.idSel, c = E.porId.get(id), recs = E.recsPorId.get(id) || [];
  const sel = recs.find((r) => r.clave === E.claveSel);
  const res = c?.resultado?.estado || "desconocido";
  $("#chatCab").innerHTML = `<h2>Consulta ${esc(id)}</h2>
    ${c?.origen?.campania ? `<span class="dato">Campaña: ${esc(c.origen.campania)}</span>` : ""}
    ${c?.propiedades?.zona_formulario ? `<span class="dato">Zona del formulario: ${esc(c.propiedades.zona_formulario)}</span>` : ""}
    <span class="dato">Resultado: ${RESULTADO[res] || esc(res)}</span>`;
  if (!c) { $("#chatCuerpo").innerHTML = `<p class="futuro-nota">La conversación completa no está disponible en este lote.</p>`; return; }
  const corte = sel ? fecha(sel.evaluado_en) : null;
  const eventos = [...c.mensajes.map((m) => ({ t: fecha(m.ts), m })), ...recs.map((r) => ({ t: fecha(r.evaluado_en), r, orden: 1 }))]
    .sort((a, b) => a.t - b.t || (a.orden || 0) - (b.orden || 0));
  let html = "", dia = "", notaFuturo = false;
  for (const ev of eventos) {
    const d = fFecha.format(ev.t);
    if (d !== dia) { html += `<div class="dia">${esc(d)}</div>`; dia = d; }
    if (ev.r) {
      const r = ev.r, cat = catInfo(catActual(r));
      html += `<button class="marca-decision${r.clave === E.claveSel ? " activa" : ""}" data-clave="${esc(r.clave)}">
        <span><i style="background:${esc(cat.color)}"></i>${esc(PUNTO[r.punto] || r.punto)}: ${esc(cat.nombre)}</span></button>`;
      continue;
    }
    const m = ev.m, futuro = corte && ev.t > corte;
    if (futuro && !notaFuturo) { html += `<p class="futuro-nota">Lo que pasó después. El sistema todavía no lo veía.</p>`; notaFuturo = true; }
    const clases = ["msj", m.autor, m.tipo === "plantilla" ? "plantilla" : "", futuro ? "futuro" : ""].join(" ");
    const tag = m.tipo === "plantilla" ? `<span class="msj-tag">Plantilla ${esc(m.plantilla_id || "")}</span>\n` : "";
    html += `<div class="${clases}">${tag}${esc(m.texto || `[${m.tipo}]`)}<span class="msj-hora">${fHora.format(ev.t)}</span></div>`;
  }
  const cuerpo = $("#chatCuerpo");
  cuerpo.innerHTML = html;
  const activa = cuerpo.querySelector(".marca-decision.activa");
  if (activa) cuerpo.scrollTop = Math.max(0, activa.offsetTop - cuerpo.offsetTop - cuerpo.clientHeight * 0.62);
}

// ---------------------------------------------------------------- lectura del sistema
function valorCompartimento(k, cl, sen) {
  if (k === "menciona_ubicacion") return cl.sede ? SEDE[cl.sede] || cl.sede : "";
  if (k === "dice_motivo") return cl.necesidad ? NECESIDAD[cl.necesidad] || cl.necesidad : "";
  if (k === "dice_cuando") {
    const u = sen.urgencia || {}, p = u.p_pronto ?? null, sc = u.score ?? 0;
    if (p !== null ? p >= 0.7 && sc >= 2.5 : sc >= 2.5) return "Esta semana";
    if (p !== null ? p >= 0.7 : sc >= 1.75) return "En 2 o 3 semanas";
    return "Más adelante";
  }
  return k === "describe_que_guarda" ? "Lo describe" : "";
}
const horas = (h) => (h < 1 ? `${Math.max(1, Math.round(h * 60))} min` : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} días`);

function pintarLectura() {
  const r = (E.recsPorId.get(E.idSel) || []).find((x) => x.clave === E.claveSel);
  const L = $("#lectura");
  if (!r) { L.innerHTML = `<p class="lectura-vacia">Elegí una consulta de la lista.</p>`; return; }
  const cl = r.clasificacion, sen = cl.senales || {}, v = r.ventana, ac = r.accion;
  const etapa = ETAPA_DE[r.punto], cid = catActual(r), cat = catInfo(cid);
  const jevCat = cl.categoria || null;
  const asig = E.datos.asignaciones?.[r.clave];
  const origen = asig ? (asig.origen === "alberto" ? "La cambiaste a mano." : asig.origen === "asistente" ? "La cambió el asistente." : "Aceptaste la sugerencia de Jev.")
    : jevCat ? `Elegida por Jev${jevCat.confianza != null ? ` (confianza ${pct(jevCat.confianza)})` : ""}.` : "Lote anterior a las categorías: equivalencia por reglas.";
  const alternativas = jevCat?.alternativas?.length
    ? `<div class="alternativas">${jevCat.alternativas.map((a) => `<span class="alt">${esc(catInfo(a.id).nombre)} ${pct(a.prob)}</span>`).join("")}</div>` : "";
  const alertas = r.punto === "primer_contacto" ? cl.alertas.filter((a) => !a.includes("pregunta")) : cl.alertas;
  const senalOculta = r.punto === "primer_contacto" ? "pregunta_sin_responder" : null;

  const ventana = v.abierta
    ? `<span class="ventana"><i></i>Ventana abierta: quedan ${Math.max(0, Math.round(v.horas_restantes))} h para escribir libremente</span>`
    : `<span class="ventana cerrada"><i></i>Ventana cerrada: solo se puede enviar una plantilla aprobada</span>`;
  const chips = [cl.necesidad ? NECESIDAD[cl.necesidad] : null, cl.sede ? `Sede ${SEDE[cl.sede] || cl.sede}` : null, cl.es_empresa === "si" ? "Empresa" : null]
    .filter(Boolean).map((t) => `<span class="dato-chip">${esc(t)}</span>`).join("");
  const opciones = [...catsDeEtapa(etapa), SIN].map((c) => `<option value="${esc(c.id)}"${c.id === cid ? " selected" : ""}>${esc(c.nombre)}</option>`).join("");

  const comps = COMPARTIMENTOS.map(([k, nombre]) => {
    const x = sen[k] || { prob: 0, lectura: "no" };
    const val = x.lectura === "si" ? valorCompartimento(k, cl, sen) : x.lectura === "duda" ? "No está claro" : "No lo dijo";
    return `<div class="comp ${x.lectura}"><span class="comp-nombre">${nombre}</span><span class="comp-valor">${esc(val)}</span><span class="comp-prob">${pct(x.prob)}</span></div>`;
  }).join("");
  const otras = Object.entries(OTRAS_SENALES).map(([k, n]) => [k, n, sen[k]]).filter(([k, , x]) => x && k !== senalOculta).sort((a, b) => b[2].prob - a[2].prob);
  const visibles = E.verTodas ? otras : otras.filter(([, , x]) => x.prob >= 0.3);
  const senalesHtml = visibles.map(([, n, x]) => `<li class="senal ${x.lectura}"><span>${esc(n)}</span><span class="barra-p"><i style="width:${pct(x.prob)}"></i></span><span class="senal-p">${pct(x.prob)}</span></li>`).join("")
    || `<li class="senal"><span style="color:var(--acero)">Ninguna otra señal fuerte.</span></li>`;

  let sug;
  if (ac.tipo === "borrador_libre") {
    const b = ac.borrador || {};
    sug = `<div class="sugerencia"><div class="sug-accion">${ACCION[ac.tipo]}</div><div class="sug-texto">${esc(b.texto)}</div>
      <div class="sug-pie"><button class="boton chico" data-copiar="${esc(b.texto)}">Copiar</button><span>Borrador${b.modelo && b.modelo !== "offline" ? ` de ${esc(b.modelo)}` : ""}: lo revisa y lo envía una persona.</span>
      ${(b.riesgos || []).map((x) => `<span class="etiqueta-mini">Revisar: ${esc(x)}</span>`).join("")}</div></div>`;
  } else if (ac.tipo === "plantilla") {
    const p = ac.plantilla;
    sug = `<div class="sugerencia plantilla"><div class="sug-accion">${ACCION[ac.tipo]}: ${esc(p.nombre_meta)}</div><div class="sug-texto">${esc(p.texto)}</div>
      <div class="sug-pie"><span>${esc(ac.motivo || "")}</span>${ac.simulada ? `<span class="etiqueta-mini">Ejemplo, no aprobada</span>` : ""}</div></div>`;
  } else {
    sug = `<div class="sugerencia neutra"><div class="sug-accion">${esc(ACCION[ac.tipo] || ac.tipo)}</div><div class="sug-texto">${esc(ac.detalle || ac.motivo || "")}</div></div>`;
  }
  const o = r.observado || {};
  const obs = `<dl class="observado">
    <dt>Ventas respondió</dt><dd>${o.siguiente_mensaje_ventas ? esc(o.siguiente_mensaje_ventas) + (o.horas_hasta_respuesta_ventas != null ? ` <span style="color:var(--acero)">(a las ${horas(o.horas_hasta_respuesta_ventas)})</span>` : "") : "No hay otro mensaje de Ventas"}</dd>
    ${o.plantilla_usada_por_ventas ? `<dt>Plantilla usada</dt><dd>${esc(o.plantilla_usada_por_ventas)}</dd>` : ""}
    <dt>El cliente</dt><dd>${o.prospecto_volvio_a_escribir ? "Volvió a escribir" : "No volvió a escribir"}</dd>
    <dt>Resultado</dt><dd>${RESULTADO[o.resultado] || "Sin dato"}</dd></dl>`;

  L.innerHTML = `
    <div class="momento"><b>${esc(PUNTO[r.punto] || r.punto)}</b><span>${esc(fCompleta.format(fecha(r.evaluado_en)))}</span></div>
    ${ventana}
    <div class="etiqueta" style="--seg:${esc(cat.color)}">
      <div class="etiqueta-nombre">${esc(cat.nombre)}</div>
      <div class="etiqueta-desc">${esc(cat.descripcion || "")}</div>
      ${chips ? `<div class="etiqueta-datos">${chips}</div>` : ""}
      ${jevCat?.revisar && !asig ? `<div class="revision-flag">Revisá la categoría: ${esc(jevCat.motivo || "Jev duda.")}</div>` : ""}
    </div>
    <div class="origen-cat">${esc(origen)}${cat.accion ? ` Acción de la categoría: ${esc(ACCION_CAT[cat.accion])}.` : ""}</div>
    ${alternativas}
    ${local() ? `<label class="cambiar-cat">Cambiar categoría <select id="selCat">${opciones}</select></label>` : ""}
    <div class="bloque"><h3>Para cotizar hace falta<small>lo que ya dijo el cliente</small></h3><div class="compartimentos">${comps}</div></div>
    <div class="bloque"><h3>Por qué</h3><ul class="porque">${cl.explicacion.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      ${alertas.length ? `<div class="alertas">${alertas.map((x) => `<div class="alerta">${esc(x)}</div>`).join("")}</div>` : ""}</div>
    <div class="bloque"><h3>Otras señales</h3><ul class="senales">${senalesHtml}</ul>
      ${otras.length > visibles.length || E.verTodas ? `<button class="ver-mas" data-ver-todas>${E.verTodas ? "Ver solo las fuertes" : `Ver todas (${otras.length})`}</button>` : ""}</div>
    <div class="bloque"><h3>Qué sugiere</h3>${sug}</div>
    <div class="bloque"><h3>Qué pasó en realidad</h3>${obs}</div>
    <div class="bloque revision" id="revision">${formRevision(r, etapa)}</div>`;
}

function formRevision(r, etapa) {
  const v = E.datos.revisiones[r.clave] || {};
  const opciones = [...catsDeEtapa(etapa), SIN].map((c) => `<option value="${esc(c.id)}"${v.segmento_correcto === c.id ? " selected" : ""}>${esc(c.nombre)}</option>`).join("");
  const nota = (n) => `<button data-nota="${n}" aria-pressed="${v.sugerencia_nota === n}">${n}</button>`;
  const et = r.etiqueta_ventas;
  return `<h3>Tu revisión</h3>
    <p class="pregunta">¿La categoría es correcta?</p>
    <div class="segmentado" role="group"><button data-ok="si" aria-pressed="${v.segmento_ok === "si"}">Sí</button><button data-ok="no" aria-pressed="${v.segmento_ok === "no"}">No</button></div>
    <div class="fila" ${v.segmento_ok === "no" ? "" : "hidden"} id="filaCorrecto"><p class="pregunta">¿Cuál era?</p><select id="segCorrecto"><option value="">Elegir</option>${opciones}</select></div>
    <div class="fila"><p class="pregunta">¿Sirve lo que sugiere?</p><div class="escala" role="group">${[1, 2, 3, 4, 5].map(nota).join("")}</div>
      <div class="escala-rotulos"><span>No sirve</span><span>Lo enviaría tal cual</span></div></div>
    <div class="fila"><p class="pregunta">Comentario</p><textarea id="comentario" placeholder="Qué cambiarías">${esc(v.comentario || "")}</textarea></div>
    <div class="guardado" id="guardado">${v.fecha ? "Guardada" : ""}</div>
    ${et?.segmento ? `<p class="pregunta" style="color:var(--acero);font-size:13px">Clasificación cargada en el lote: <b style="color:var(--tinta)">${esc(catInfo(LEGADO[et.segmento] || et.segmento).nombre === "Sin categoría" ? et.segmento : catInfo(LEGADO[et.segmento] || et.segmento).nombre)}</b>${et.revisado_por === "simulado" ? " (simulada)" : ""}</p>` : ""}`;
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
    const li = document.querySelector(`.item[data-id="${CSS.escape(E.idSel)}"] .item-inf`);
    if (li) li.innerHTML = itemInf(E.idSel);
  } catch (e) { $("#guardado").textContent = `No se pudo guardar: ${e.message}`; }
}

async function moverCategoria(clave, categoria) {
  try {
    await post("api/mover", { lote: E.corrida, clave, categoria });
    E.datos.asignaciones[clave] = { categoria, origen: "alberto" };
    toast(`Movida a ${catInfo(categoria).nombre}`);
    pintarFiltros(); pintarLista(); seleccionar(E.idSel, clave);
  } catch (e) { toast(e.message); }
}

// ---------------------------------------------------------------- categorías
function ultimosPorContacto(etapa) {
  const ult = new Map();
  for (const r of [...E.datos.recomendaciones].sort((a, b) => a.evaluado_en.localeCompare(b.evaluado_en)))
    if (ETAPA_DE[r.punto] === etapa) ult.set(r.id_consulta, r);
  return [...ult.values()];
}

function pintarCategorias() {
  const V = $("#vista-categorias");
  if (!E.cats || !E.datos) { V.innerHTML = ""; return; }
  const pend = (E.datos.reasignaciones || []).filter((x) => x.estado === "pendiente");
  const pendHtml = pend.length ? `<div class="pendientes"><h2>${pend.length} ${pend.length === 1 ? "contacto quedó" : "contactos quedaron"} sin categoría</h2>
    <p>Se eliminó la categoría en la que estaban. Jev sugiere la que mejor les queda entre las que siguen: aceptala o elegí otra.</p>
    ${pend.map((x) => {
      const c = E.porId.get(x.id_consulta);
      const primer = c ? (c.mensajes.find((m) => m.autor === "cliente") || {}).texto : x.id_consulta;
      const opts = catsDeEtapa(ETAPA_DE[x.momento]).map((k) => `<option value="${esc(k.id)}">${esc(k.nombre)}</option>`).join("");
      return `<div class="pend-fila" data-clave="${esc(x.clave)}"><span class="texto" title="${esc(primer)}"><b>${esc(x.id_consulta)}</b> ${esc(primer)}</span>
        <span class="sug">Estaba en ${esc(x.de_nombre)}. ${x.sugerida ? `Jev sugiere <b>${esc(x.sugerida_nombre)}</b> <small>${x.confianza != null ? pct(x.confianza) : ""}</small>` : "Jev no pudo sugerir: elegí a mano."}</span>
        <span class="pend-botones">${x.sugerida ? `<button class="boton chico" data-aceptar>Aceptar</button>` : ""}
          <select aria-label="Elegir otra categoría" data-otra><option value="">Elegir otra</option>${opts}</select></span></div>`;
    }).join("")}</div>` : "";

  const etapas = Object.entries(E.cats.etapas).map(([etapa, nombreEtapa]) => {
    const recs = ultimosPorContacto(etapa);
    const por = {};
    recs.forEach((r) => { const k = catActual(r); (por[k] = por[k] || []).push(r); });
    const lista = [...catsDeEtapa(etapa), ...(por.sin_categoria ? [SIN] : [])];
    return `<section class="etapa"><h2>${esc(nombreEtapa)}</h2>
      <p class="nota">${etapa === "primer_contacto" ? "Se clasifica con el primer mensaje del prospecto." : "Se clasifica cuando pasan 24 h sin respuesta o el prospecto vuelve a escribir."} ${recs.length} contactos en este lote.</p>
      ${lista.map((c) => {
        const miembros = por[c.id] || [];
        const abierta = E.abiertas.has(c.id);
        const plantillas = (c.plantillas || []).length ? `<span class="dato-chip">Plantillas: ${c.plantillas.map(esc).join(", ")}</span>` : "";
        return `<article class="cat" style="--c:${esc(c.color)}" data-cat="${esc(c.id)}"><span class="cat-banda"></span><div class="cat-cuerpo">
          <div class="cat-sup"><span class="cat-nombre">${esc(c.nombre)}</span><span class="cat-n">${miembros.length} ${miembros.length === 1 ? "contacto" : "contactos"}</span></div>
          <p class="cat-desc">${esc(c.descripcion)}</p>
          <div class="cat-meta">${c.accion ? `<span class="dato-chip">${esc(ACCION_CAT[c.accion])}</span>` : ""}${plantillas}</div>
          <div class="cat-botones">
            ${miembros.length ? `<button class="boton-texto" data-ver>${abierta ? "Ocultar contactos" : "Ver contactos"}</button>` : ""}
            ${local() && c.id !== "sin_categoria" ? `<span style="flex:1"></span><button class="boton chico" data-editar>Editar</button><button class="boton chico peligro" data-eliminar>Eliminar</button>` : ""}
          </div>
          ${abierta ? `<ul class="cat-miembros">${miembros.map((r) => {
            const k = E.porId.get(r.id_consulta);
            const t = k ? (k.mensajes.filter((m) => m.autor === "cliente").slice(-1)[0] || {}).texto : "";
            return `<li data-ir="${esc(r.id_consulta)}" data-clave="${esc(r.clave)}"><span>${esc(r.id_consulta)}</span><span>${esc(t || "")}</span></li>`;
          }).join("")}</ul>` : ""}
        </div></article>`;
      }).join("")}
      ${local() ? `<button class="boton" data-nueva="${esc(etapa)}">Nueva categoría</button>` : ""}
    </section>`;
  }).join("");

  V.innerHTML = `<div class="cats">
    <div class="cats-cab"><div><h1>Categorías</h1>
      <p class="bajada">Jev lee la descripción de cada categoría y ubica ahí a cada contacto. Escribí las descripciones como situaciones que se ven en la conversación. Si cambiás descripciones, reclasificá el lote para que Jev vuelva a ubicarlos; los cambios que hiciste a mano se mantienen.</p></div>
      ${local() ? `<div class="cats-acciones"><button class="boton" id="btnReclasificar">Reclasificar este lote con Jev</button></div>` : `<p class="bajada">En la versión de demostración no se pueden editar.</p>`}
    </div>
    ${pendHtml}
    <div class="etapas">${etapas}</div></div>`;
}

function abrirCategoria(cat, etapa) {
  const nueva = !cat;
  const c = cat || { etapa, nombre: "", descripcion: "", accion: etapa === "post_24h" ? "plantilla" : "responder", color: "#3F5873", plantillas: [] };
  $("#catTitulo").textContent = nueva ? `Nueva categoría: ${E.cats.etapas[etapa]}` : `Editar: ${c.nombre}`;
  const plantillas = (E.plantillasIds || []).map((p) => `<label><input type="checkbox" value="${esc(p)}"${(c.plantillas || []).includes(p) ? " checked" : ""}> ${esc(p)}</label>`).join("");
  $("#catCuerpo").innerHTML = `<form class="form-cat" id="formCat">
    <div class="dos"><label>Nombre<input name="nombre" value="${esc(c.nombre)}" required maxlength="60"></label>
      <label>Color<input name="color" type="color" value="${esc(c.color)}"></label></div>
    <label>Descripción para Jev<textarea name="descripcion" required>${esc(c.descripcion)}</textarea>
      <small>Contá qué dice o hace el prospecto, en una o dos frases. Ejemplo: «El prospecto pregunta si puede visitar la sede antes de decidir».</small></label>
    <label>Qué hacer con estos contactos<select name="accion">${Object.entries(ACCION_CAT).map(([k, n]) => `<option value="${k}"${c.accion === k ? " selected" : ""}>${n}</option>`).join("")}</select></label>
    ${plantillas ? `<div class="plantillas-check"><span>Plantillas preferidas (cuando la ventana está cerrada)</span>${plantillas}</div>` : ""}
    <p id="catError" class="nota-alerta" hidden></p>
    <div class="dlg-pie"><button type="button" class="boton" data-cancelar>Cancelar</button><button class="boton primario">${nueva ? "Crear categoría" : "Guardar cambios"}</button></div>
  </form>`;
  const f = $("#formCat");
  f.querySelector("[data-cancelar]").onclick = () => $("#dlgCategoria").close();
  f.onsubmit = async (e) => {
    e.preventDefault();
    const datos = { nombre: f.nombre.value, descripcion: f.descripcion.value, accion: f.accion.value, color: f.color.value,
      plantillas: [...f.querySelectorAll(".plantillas-check input:checked")].map((x) => x.value) };
    try {
      if (nueva) await post("api/categorias/crear", { categoria: { ...datos, etapa } });
      else await post("api/categorias/editar", { id: c.id, cambios: datos });
      $("#dlgCategoria").close();
      toast(nueva ? "Categoría creada" : "Categoría guardada");
      await recargarTodo();
    } catch (err) { const p = $("#catError"); p.textContent = err.message; p.hidden = false; }
  };
  $("#dlgCategoria").showModal();
}

async function eliminarCategoria(id) {
  const c = catInfo(id);
  const n = ultimosPorContacto(c.etapa).filter((r) => catActual(r) === id).length;
  const msg = `¿Eliminar «${c.nombre}»?` + (n ? `\n\n${n} ${n === 1 ? "contacto queda" : "contactos quedan"} sin categoría. Jev va a sugerir la que mejor les queda y vas a poder aceptarla o elegir otra.` : "");
  if (!confirm(msg)) return;
  try {
    toast("Eliminando y pidiendo sugerencias a Jev…");
    const r = await post("api/categorias/eliminar", { id });
    await recargarTodo();
    toast(r.contactos_a_reasignar ? `${r.contactos_a_reasignar} contactos esperan tu confirmación` : `Se eliminó ${r.eliminada}`);
    if (r.errores?.length) alert(r.errores.join("\n"));
  } catch (e) { alert(e.message); }
}

// ---------------------------------------------------------------- resumen
function pintarResumen() {
  const d = E.datos, recs = d.recomendaciones, primeros = recs.filter((r) => r.punto === "primer_contacto");
  const conEt = primeros.filter((r) => r.etiqueta_ventas?.segmento);
  const etCat = (r) => LEGADO[r.etiqueta_ventas.segmento] || r.etiqueta_ventas.segmento;
  const decididos = conEt.filter((r) => catActual(r) !== "sin_categoria");
  const aciertos = decididos.filter((r) => catActual(r) === etCat(r)).length;
  const revs = Object.values(d.revisiones), revSeg = revs.filter((v) => v.segmento_ok), revOk = revSeg.filter((v) => v.segmento_ok === "si").length;
  const notas = revs.map((v) => v.sugerencia_nota).filter(Boolean);
  const notaProm = notas.length ? (notas.reduce((a, b) => a + b, 0) / notas.length).toFixed(1).replace(".", ",") : "–";
  const m = d.meta || {};
  const titulo = conEt.length ? `El sistema coincidió con Ventas en ${aciertos} de ${decididos.length} primeros mensajes` : `${primeros.length} consultas clasificadas`;
  const barras = (cuenta, orden, color) => {
    const max = Math.max(1, ...Object.values(cuenta));
    return orden.filter((s) => cuenta[s]).map((s) => `<div class="barra-fila"><span>${esc(catInfo(s).nombre)}</span>
      <span class="pista"><i style="width:${(100 * cuenta[s]) / max}%;background:${esc(color || catInfo(s).color)}"></i></span><span class="num">${cuenta[s]}</span></div>`).join("");
  };
  const cuenta = {}, cuentaPost = {};
  primeros.forEach((r) => { const k = catActual(r); cuenta[k] = (cuenta[k] || 0) + 1; });
  ultimosPorContacto("post_24h").forEach((r) => { const k = catActual(r); cuentaPost[k] = (cuentaPost[k] || 0) + 1; });
  const ordenP = [...catsDeEtapa("primer_contacto").map((c) => c.id), "sin_categoria"], ordenQ = [...catsDeEtapa("post_24h").map((c) => c.id), "sin_categoria"];
  const acc = {};
  recs.forEach((r) => { acc[r.accion.tipo] = (acc[r.accion.tipo] || 0) + 1; });
  const maxA = Math.max(1, ...Object.values(acc));
  const acciones = Object.entries(acc).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<div class="barra-fila"><span>${esc(ACCION[k] || k)}</span>
    <span class="pista"><i style="width:${(100 * n) / maxA}%;background:var(--petroleo)"></i></span><span class="num">${n}</span></div>`).join("");
  const resSeg = {};
  primeros.forEach((r) => { const s = catActual(r), o = r.observado?.resultado || "desconocido"; resSeg[s] = resSeg[s] || { alquilo: 0, no_alquilo: 0, desconocido: 0 }; resSeg[s][o]++; });
  const COL = { alquilo: "#127A4A", no_alquilo: "#B9C1BC", desconocido: "#E3E7E4" };
  const resultados = ordenP.filter((s) => resSeg[s]).map((s) => {
    const x = resSeg[s], tot = x.alquilo + x.no_alquilo + x.desconocido;
    return `<div class="barra-fila"><span>${esc(catInfo(s).nombre)}</span><span class="pista">${["alquilo", "no_alquilo", "desconocido"].map((k) => `<i style="width:${(100 * x[k]) / tot}%;background:${COL[k]}" title="${RESULTADO[k]}: ${x[k]}"></i>`).join("")}</span><span class="num">${pct(x.alquilo / tot)}</span></div>`;
  }).join("");
  let matriz = "";
  if (conEt.length) {
    const segs = ordenP.filter((s) => conEt.some((r) => etCat(r) === s || catActual(r) === s));
    const celda = {};
    conEt.forEach((r) => { const k = `${etCat(r)}|${catActual(r)}`; celda[k] = (celda[k] || 0) + 1; });
    const maxC = Math.max(1, ...Object.values(celda));
    matriz = `<div class="panel ancho"><h2>Dónde coincide y dónde no</h2><p class="nota">Cada fila es lo que dijo Ventas; cada columna, lo que dijo el sistema. La diagonal son los aciertos.</p>
      <div style="overflow-x:auto"><table class="matriz"><thead><tr><th></th>${segs.map((s) => `<th>${esc(catInfo(s).nombre)}</th>`).join("")}</tr></thead><tbody>
      ${segs.map((f) => `<tr><th class="fila">${esc(catInfo(f).nombre)}</th>${segs.map((c) => {
        const n = celda[`${f}|${c}`] || 0, a = n / maxC, diag = f === c;
        const bg = n ? (diag ? `rgba(31,94,87,${0.12 + a * 0.75})` : `rgba(180,83,42,${0.12 + a * 0.6})`) : "#F6F7F6";
        return `<td class="${diag ? "diag" : ""}" style="background:${bg};color:${a > 0.5 ? "#fff" : "inherit"}">${n || ""}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table></div></div>`;
  }
  $("#vista-resumen").innerHTML = `<div class="resumen"><h1>${esc(titulo)}</h1>
    <p class="bajada">${m.sinteticas ? "Las conversaciones de este lote son inventadas. " : ""}${m.jev === "simulado" ? "Jev está simulado: estos números solo muestran cómo se van a leer los resultados. " : ""}El acuerdo se mide sobre el primer mensaje; los contactos sin categoría no cuentan como aciertos ni como errores.</p>
    <div class="cifras">
      <div class="cifra"><b>${conEt.length ? pct(aciertos / Math.max(1, decididos.length)) : "–"}</b><span>Coincide con Ventas</span></div>
      <div class="cifra"><b>${primeros.filter((r) => catActual(r) === "sin_categoria").length}</b><span>Sin categoría</span></div>
      <div class="cifra"><b>${revs.length} <span style="font-size:15px;color:var(--acero)">de ${recs.length}</span></b><span>Sugerencias revisadas por vos</span></div>
      <div class="cifra"><b>${revSeg.length ? pct(revOk / revSeg.length) : "–"}</b><span>Correctas según tus revisiones${notas.length ? `, nota media ${notaProm}` : ""}</span></div>
    </div>
    <div class="grilla">
      <div class="panel"><h2>Primer contacto</h2><p class="nota">${primeros.length} consultas</p><div class="barras">${barras(cuenta, ordenP)}</div></div>
      <div class="panel"><h2>Después de 24 h</h2><p class="nota">Último momento de cada contacto</p><div class="barras">${barras(cuentaPost, ordenQ) || `<p class="nota">Todavía no pasaron 24 h en ningún contacto.</p>`}</div></div>
      ${matriz}
      <div class="panel"><h2>Qué sugirió hacer</h2><p class="nota">${recs.length} momentos en que había que decidir algo</p><div class="barras">${acciones}</div></div>
      <div class="panel"><h2>Cuántos alquilaron, según cómo empezaron</h2><p class="nota">Muestra si las categorías separan bien. No prueba que el sistema cause ventas.</p>
        <div class="leyenda"><span style="--c:${COL.alquilo}">Alquiló</span><span style="--c:${COL.no_alquilo}">No alquiló</span><span style="--c:#D5DAD6">Sin dato</span></div>
        <div class="barras">${resultados}</div></div>
    </div>
    <div class="resumen-acciones">${local() ? `<a class="boton" href="api/revisiones.csv?nombre=${encodeURIComponent(E.corrida)}">Descargar tus revisiones (CSV)</a>` : `<button class="boton" id="btnCsvDemo">Descargar tus revisiones (CSV)</button>`}</div></div>`;
}

function descargarCsvDemo() {
  const filas = [["id_consulta", "momento", "evaluado_en", "categoria_sistema", "clasificacion_ok", "categoria_correcta", "accion", "nota_sugerencia", "comentario"]];
  for (const r of E.datos.recomendaciones) {
    const v = E.datos.revisiones[r.clave];
    if (v) filas.push([r.id_consulta, r.punto, r.evaluado_en, catInfo(catActual(r)).nombre, v.segmento_ok || "", v.segmento_correcto || "", r.accion.tipo, v.sugerencia_nota || "", v.comentario || ""]);
  }
  const csv = "﻿" + filas.map((f) => f.map((x) => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `revisiones_${E.corrida}.csv`;
  a.click();
}

// ---------------------------------------------------------------- importar archivos
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
  $("#btnImportar").disabled = true;
  est.textContent = "Leyendo archivos…";
  try {
    const archivos = await Promise.all(archivosElegidos.map(async (f) => ({ nombre: f.name, contenido: await f.text() })));
    est.textContent = "Clasificando conversaciones. Puede tardar un poco.";
    const r = await post("api/importar", { archivos, jev: document.querySelector("input[name=jev]:checked").value,
      simular_plantillas: $("#simularPlantillas").checked, nombres_ventas: $("#nombresVentas").value, etiqueta: $("#etiquetaLote").value });
    archivosElegidos.length = 0; pintarArchivos();
    est.textContent = `Listo: ${r.consultas} consultas clasificadas.`;
    await recargarTodo(r.lote);
    mostrarVista("consultas");
    toast(`Lote ${r.lote} creado`);
  } catch (e) { est.textContent = e.message; est.classList.add("error"); }
  finally { $("#btnImportar").disabled = !archivosElegidos.length; }
}

// ---------------------------------------------------------------- agregar lote (pegar)
function bloqueContacto(n) {
  return `<div class="contacto" data-n="${n}"><div class="contacto-cab"><span>Contacto ${n}</span>${n > 1 ? `<button class="boton-texto" data-quitar>Quitar</button>` : ""}</div>
    <textarea placeholder="Pegá la conversación. Ejemplo:&#10;Cliente: Hola, necesito una baulera en Palermo para el mes que viene&#10;Ventas: ¡Hola! ¿Qué te gustaría guardar?"></textarea>
    <div class="contacto-datos">
      <label>Nombre del contacto (se borra del texto)<input data-campo="nombre" type="text"></label>
      <label>Último mensaje hace (horas)<input data-campo="ultimo_hace_horas" type="number" min="0" step="1" value="0"></label>
      <label>Resultado, si lo sabés<select data-campo="resultado"><option value="desconocido">No se sabe</option><option value="alquilo">Alquiló</option><option value="no_alquilo">No alquiló</option></select></label>
    </div></div>`;
}
function abrirAgregarLote() {
  const cont = $("#loteContactos");
  if (!cont.children.length) cont.innerHTML = [1, 2, 3, 4, 5].map(bloqueContacto).join("");
  avisoJevLote();
  $("#loteEstado").textContent = "";
  $("#dlgLote").showModal();
}
function avisoJevLote() {
  const real = document.querySelector("input[name=loteJev]:checked").value === "api";
  const a = E.ajustes || {};
  const falta = !a.envio_externo_aprobado ? "activar en Ajustes que Don Box aprobó enviar conversaciones anonimizadas" : !a.typesafe?.configurada ? "cargar la clave de TypeSafe en Ajustes" : "";
  const p = $("#loteAvisoJev");
  p.hidden = !(real && falta);
  p.innerHTML = real && falta ? `Para usar Jev real falta ${falta}. <button class="boton-texto" data-ir-ajustes>Abrir Ajustes</button>` : "";
}
async function clasificarLote() {
  const contactos = [...document.querySelectorAll("#loteContactos .contacto")].map((b) => ({
    texto: b.querySelector("textarea").value,
    nombre: b.querySelector("[data-campo=nombre]").value,
    ultimo_hace_horas: Number(b.querySelector("[data-campo=ultimo_hace_horas]").value || 0),
    resultado: b.querySelector("[data-campo=resultado]").value,
  })).filter((c) => c.texto.trim());
  const est = $("#loteEstado");
  est.classList.remove("error");
  if (!contactos.length) { est.textContent = "Pegá al menos una conversación."; est.classList.add("error"); return; }
  const real = document.querySelector("input[name=loteJev]:checked").value === "api";
  $("#btnClasificarLote").disabled = true;
  est.textContent = real ? "Clasificando con Jev real…" : "Clasificando…";
  try {
    const r = await post("api/lote/agregar", { contactos, etiqueta: $("#loteNombre").value || "contactos", jev_real: real, simular_plantillas: true });
    $("#dlgLote").close();
    $("#loteContactos").innerHTML = "";
    await recargarTodo(r.lote);
    mostrarVista("consultas");
    toast(`Listo: ${r.consultas} contactos clasificados${r.errores?.length ? ` (${r.errores.length} con error)` : ""}`);
  } catch (e) { est.textContent = e.message; est.classList.add("error"); }
  finally { $("#btnClasificarLote").disabled = false; }
}

// ---------------------------------------------------------------- ajustes
function pintarAjustes() {
  const a = E.ajustes;
  const provs = Object.entries(a.proveedores);
  const opciones = (sel, extra) => [...(extra || []), ...provs.filter(([, p]) => p.configurada).map(([k, p]) => [k, p.nombre])]
    .map(([k, n]) => `<option value="${k}"${sel === k ? " selected" : ""}>${esc(n)}</option>`).join("");
  $("#ajustesCuerpo").innerHTML = `
    <div class="ajustes-seccion"><label class="interruptor"><input type="checkbox" id="ajAprobado"${a.envio_externo_aprobado ? " checked" : ""}>
      <span><b>Don Box aprobó enviar conversaciones anonimizadas a proveedores externos</b><br><small style="color:var(--acero)">Sin esto, Jev real, los borradores con IA y el chat quedan apagados. Antes de enviar se borran teléfonos, emails, DNI y nombres.</small></span></label></div>
    <div class="ajustes-seccion"><h3>Jev (TypeSafe)</h3><p>Clasifica las conversaciones. ${a.typesafe.configurada ? `<span class="estado-ok">Clave cargada${a.typesafe.desde_entorno ? " (desde la variable de entorno)" : ""}.</span>` : `<span class="estado-no">Falta la clave.</span>`}</p>
      <div class="prov"><span>Clave</span><input type="password" data-clave="typesafe" placeholder="${a.typesafe.configurada ? "Dejar vacío para no cambiarla" : "Pegá la clave de TypeSafe"}" autocomplete="off"></div></div>
    <div class="ajustes-seccion"><h3>Modelos de IA</h3><p>Para el chat asistente y los borradores. Se usan API keys, que se pagan por uso (centavos). Las suscripciones como ChatGPT Plus o Claude Pro no se pueden conectar a apps propias.</p>
      ${provs.map(([k, p]) => `<div class="prov"><span>${esc(p.nombre)}<br><small class="${p.configurada ? "estado-ok" : "estado-no"}">${p.configurada ? "Clave cargada" : esc(p.ayuda)}</small></span>
        <input type="password" data-clave="${k}" placeholder="${p.configurada ? "Dejar vacío para no cambiarla" : "API key"}" autocomplete="off">
        <input type="text" data-modelo="${k}" value="${esc(p.modelo)}" aria-label="Modelo de ${esc(p.nombre)}"></div>`).join("")}
      <div class="fila-sel"><span>Chat asistente con</span><select id="ajChat">${opciones(a.proveedor_chat)}</select></div>
      <div class="fila-sel"><span>Borradores con</span><select id="ajBorr">${opciones(a.proveedor_borradores, [["offline", "Textos base (sin IA)"]])}</select></div>
    </div>
    <div class="dlg-pie"><span id="ajEstado" class="importar-estado"></span><button class="boton primario" id="btnGuardarAjustes">Guardar</button></div>`;
}
async function guardarAjustes() {
  const claves = {}, modelos = {};
  document.querySelectorAll("#ajustesCuerpo [data-clave]").forEach((i) => { if (i.value.trim()) claves[i.dataset.clave] = i.value.trim(); });
  document.querySelectorAll("#ajustesCuerpo [data-modelo]").forEach((i) => { modelos[i.dataset.modelo] = i.value.trim(); });
  try {
    E.ajustes = await post("api/ajustes", { cambios: { envio_externo_aprobado: $("#ajAprobado").checked, claves, modelos,
      proveedor_chat: $("#ajChat")?.value || undefined, proveedor_borradores: $("#ajBorr")?.value || undefined } });
    pintarAjustes(); pintarProveedoresChat(); avisoJevLote();
    $("#ajEstado").textContent = "Guardado.";
  } catch (e) { $("#ajEstado").textContent = e.message; }
}

// ---------------------------------------------------------------- asistente
const SUGERENCIAS = [
  "¿Cuántos contactos hay en cada categoría de este lote?",
  "Creá una categoría de primer contacto para los que preguntan si pueden visitar la sede",
  "Mostrame los que quieren reservar",
  "Reescribí la descripción de «Exploratoria» para que sea más clara",
];
function pintarProveedoresChat() {
  if (!E.ajustes) return;
  const ps = Object.entries(E.ajustes.proveedores).filter(([, p]) => p.configurada);
  $("#asisProveedor").innerHTML = ps.length ? ps.map(([k, p]) => `<option value="${k}"${E.ajustes.proveedor_chat === k ? " selected" : ""}>${esc(p.nombre)} (${esc(p.modelo)})</option>`).join("")
    : `<option value="">Sin modelo: cargá una clave en Ajustes</option>`;
}
function pintarChatAsistente(pensando) {
  const M = $("#asisMensajes");
  if (!E.chat.length) {
    M.innerHTML = `<div class="asis-vacio">Pedile cosas en lenguaje natural: crear o editar categorías, ver quiénes están en cada una, mover contactos o reclasificar el lote. Jev sigue siendo quien clasifica.
      <ul>${SUGERENCIAS.map((s) => `<li><button data-sug="${esc(s)}">${esc(s)}</button></li>`).join("")}</ul></div>`;
  } else {
    M.innerHTML = E.chat.map((m, i) => {
      if (m.tipo === "confirmar") return `<div class="confirmar">¿Eliminar la categoría «${esc(m.nombre)}»? ${esc(m.motivo || "")}<div>
        ${m.hecho ? `<span>${esc(m.hecho)}</span>` : `<button class="boton chico peligro" data-confirmar="${i}">Eliminar</button><button class="boton chico" data-descartar="${i}">No</button>`}</div></div>`;
      const pasos = m.pasos?.length ? `<details class="pasos"><summary>${m.pasos.length} ${m.pasos.length === 1 ? "acción" : "acciones"}</summary>${m.pasos.map((p) => `<code>${esc(p.herramienta)} ${esc(JSON.stringify(p.argumentos))}</code>`).join("")}</details>` : "";
      return `<div class="burbuja ${m.rol}">${esc(m.texto)}${pasos}</div>`;
    }).join("") + (pensando ? `<div class="pensando">Pensando…</div>` : "");
  }
  M.scrollTop = M.scrollHeight;
}
async function enviarChat(texto) {
  texto = texto.trim();
  if (!texto) return;
  E.chat.push({ rol: "user", texto });
  $("#asisTexto").value = "";
  pintarChatAsistente(true);
  try {
    const historial = E.chat.filter((m) => m.rol === "user" || (m.rol === "assistant" && m.texto)).map((m) => ({ rol: m.rol, texto: m.texto }));
    const r = await post("api/chat", { historial, lote: E.corrida, proveedor: $("#asisProveedor").value || null });
    E.chat.push({ rol: "assistant", texto: r.texto || "Listo.", pasos: r.pasos });
    (r.confirmaciones || []).forEach((c) => E.chat.push({ tipo: "confirmar", ...c }));
    if (r.cambios) await recargarTodo();
    for (const u of r.ui || []) await aplicarUI(u);
  } catch (e) { E.chat.push({ rol: "error", texto: e.message }); }
  pintarChatAsistente(false);
}
async function aplicarUI(u) {
  if (u.lote && u.lote !== E.corrida && E.corridas.some((c) => c.nombre === u.lote)) { await cargarCorrida(u.lote); pintarCorridas(); }
  if (u.vista) mostrarVista(u.vista);
  if (u.categoria) {
    if (u.vista === "categorias") { E.abiertas.add(u.categoria); pintarCategorias(); document.querySelector(`[data-cat="${CSS.escape(u.categoria)}"]`)?.scrollIntoView({ block: "center" }); }
    else { E.filtro = u.categoria; pintarFiltros(); pintarLista(); if (E.lista[0]) seleccionar(E.lista[0].id); }
  }
  if (u.id_consulta && E.recsPorId.has(u.id_consulta)) { mostrarVista("consultas"); seleccionar(u.id_consulta); }
}
function toggleChat(abrir) {
  const a = $("#asistente");
  a.hidden = abrir === undefined ? !a.hidden : !abrir;
  $("#btnChat").setAttribute("aria-expanded", String(!a.hidden));
  if (!a.hidden) { pintarProveedoresChat(); pintarChatAsistente(); $("#asisTexto").focus(); }
}

// ---------------------------------------------------------------- vistas y eventos
function mostrarVista(v) {
  E.vista = v;
  for (const n of ["consultas", "categorias", "resumen", "importar"]) $(`#vista-${n}`).hidden = n !== v;
  document.querySelectorAll(".pestana").forEach((b) => b.classList.toggle("activa", b.dataset.vista === v));
  repintarVista();
}
function repintarVista() {
  if (!E.datos) return;
  if (E.vista === "resumen") pintarResumen();
  if (E.vista === "categorias") pintarCategorias();
}
function moverSeleccion(delta) {
  const i = E.lista.findIndex((x) => x.id === E.idSel);
  const sig = E.lista[Math.min(E.lista.length - 1, Math.max(0, i + delta))];
  if (sig && sig.id !== E.idSel) { seleccionar(sig.id); document.querySelector(`.item[data-id="${CSS.escape(sig.id)}"]`)?.scrollIntoView({ block: "nearest" }); }
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
  $("#items").addEventListener("keydown", (e) => { if (e.key === "Enter") { const li = e.target.closest(".item"); if (li) seleccionar(li.dataset.id); } });
  document.addEventListener("keydown", (e) => {
    if ($("#vista-consultas").hidden || document.querySelector("dialog[open]") || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
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
    if (t.matches("[data-nota]")) actualizarRevision({ sugerencia_nota: t.getAttribute("aria-pressed") === "true" ? null : Number(t.dataset.nota) });
  });
  $("#lectura").addEventListener("change", (e) => {
    if (e.target.id === "segCorrecto") actualizarRevision({ segmento_correcto: e.target.value || null });
    if (e.target.id === "comentario") actualizarRevision({ comentario: e.target.value });
    if (e.target.id === "selCat") moverCategoria(E.claveSel, e.target.value);
  });
  $("#vista-resumen").addEventListener("click", (e) => { if (e.target.id === "btnCsvDemo") descargarCsvDemo(); });

  // categorías
  $("#vista-categorias").addEventListener("click", async (e) => {
    const t = e.target, art = t.closest("[data-cat]"), cid = art?.dataset.cat;
    if (t.matches("[data-ver]")) { E.abiertas.has(cid) ? E.abiertas.delete(cid) : E.abiertas.add(cid); pintarCategorias(); }
    if (t.matches("[data-editar]")) abrirCategoria(E.catPorId.get(cid));
    if (t.matches("[data-eliminar]")) eliminarCategoria(cid);
    if (t.matches("[data-nueva]")) abrirCategoria(null, t.dataset.nueva);
    const li = t.closest("[data-ir]");
    if (li) { mostrarVista("consultas"); E.filtro = null; pintarFiltros(); pintarLista(); seleccionar(li.dataset.ir, li.dataset.clave); }
    if (t.id === "btnReclasificar") {
      if (!confirm("Jev va a volver a elegir la categoría de cada contacto de este lote con las descripciones actuales. Los cambios que hiciste a mano se mantienen. ¿Seguir?")) return;
      t.disabled = true; t.textContent = "Reclasificando…";
      try { const r = await post("api/reclasificar", { lote: E.corrida }); await recargarTodo(); toast(`Listo: cambiaron ${r.cambiaron} de ${r.momentos}`); }
      catch (err) { alert(err.message); t.disabled = false; t.textContent = "Reclasificar este lote con Jev"; }
    }
    if (t.matches("[data-aceptar]")) {
      const fila = t.closest("[data-clave]");
      try { await post("api/reasignacion", { lote: E.corrida, clave: fila.dataset.clave, aceptar: true }); await recargarTodo(); toast("Sugerencia aceptada"); } catch (err) { alert(err.message); }
    }
  });
  $("#vista-categorias").addEventListener("change", async (e) => {
    if (!e.target.matches("[data-otra]") || !e.target.value) return;
    const fila = e.target.closest("[data-clave]");
    try { await post("api/reasignacion", { lote: E.corrida, clave: fila.dataset.clave, aceptar: false, categoria: e.target.value }); await recargarTodo(); toast(`Movido a ${catInfo(e.target.value).nombre}`); }
    catch (err) { alert(err.message); }
  });

  // agregar lote
  $("#btnAgregarLote").addEventListener("click", abrirAgregarLote);
  $("#btnMasContacto").addEventListener("click", () => {
    const cont = $("#loteContactos");
    cont.insertAdjacentHTML("beforeend", bloqueContacto(cont.children.length + 1));
    cont.lastElementChild.querySelector("textarea").focus();
  });
  $("#loteContactos").addEventListener("click", (e) => { if (e.target.matches("[data-quitar]")) e.target.closest(".contacto").remove(); });
  document.querySelectorAll("input[name=loteJev]").forEach((r) => r.addEventListener("change", avisoJevLote));
  $("#loteAvisoJev").addEventListener("click", (e) => { if (e.target.matches("[data-ir-ajustes]")) abrirAjustes(); });
  $("#btnClasificarLote").addEventListener("click", clasificarLote);

  // ajustes
  $("#btnAjustes").addEventListener("click", abrirAjustes);
  $("#ajustesCuerpo").addEventListener("click", (e) => { if (e.target.id === "btnGuardarAjustes") guardarAjustes(); });

  // asistente
  $("#btnChat").addEventListener("click", () => toggleChat());
  $("#asisCerrar").addEventListener("click", () => toggleChat(false));
  $("#asisForm").addEventListener("submit", (e) => { e.preventDefault(); enviarChat($("#asisTexto").value); });
  $("#asisTexto").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviarChat($("#asisTexto").value); } });
  $("#asisMensajes").addEventListener("click", async (e) => {
    const t = e.target;
    if (t.matches("[data-sug]")) enviarChat(t.dataset.sug);
    if (t.matches("[data-descartar]")) { E.chat[+t.dataset.descartar].hecho = "No se eliminó."; pintarChatAsistente(); }
    if (t.matches("[data-confirmar]")) {
      const m = E.chat[+t.dataset.confirmar];
      try {
        const r = await post("api/categorias/eliminar", { id: m.id });
        m.hecho = `Eliminada. ${r.contactos_a_reasignar ? `${r.contactos_a_reasignar} contactos esperan tu confirmación en Categorías.` : ""}`;
        await recargarTodo(); mostrarVista("categorias");
      } catch (err) { m.hecho = err.message; }
      pintarChatAsistente();
    }
  });

  // importar
  const zona = $("#zona");
  zona.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#archivos").click(); } });
  $("#archivos").addEventListener("change", (e) => { agregarArchivos(e.target.files); e.target.value = ""; });
  ["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("encima"); }));
  ["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove("encima"); }));
  zona.addEventListener("drop", (e) => agregarArchivos(e.dataTransfer.files));
  $("#btnImportar").addEventListener("click", importar);
}

async function abrirAjustes() {
  try { E.ajustes = await pedir("api/ajustes"); } catch { /* sin servidor */ }
  if (!E.ajustes) return;
  pintarAjustes();
  $("#dlgAjustes").showModal();
}

async function iniciar() {
  eventos();
  try { await detectarModo(); }
  catch { $("#lectura").innerHTML = `<p class="lectura-vacia">No se encontraron lotes. Abrí el panel con <code>python scripts/abrir_panel.py</code>.</p>`; return; }
  if (!local()) {
    for (const id of ["#btnAgregarLote", "#btnAjustes", "#btnChat"]) { $(id).disabled = true; $(id).title = "Solo en el panel local (python scripts/abrir_panel.py)"; }
    $("#vista-importar .importar").innerHTML = `<h1>Importar conversaciones</h1>
      <p class="bajada">Esta es la versión de demostración publicada en internet: no recibe archivos, para que ninguna conversación real quede en un sitio público. Para importar, agregar lotes, editar categorías o usar el asistente, abrí el panel en tu computadora con <code>python scripts/abrir_panel.py</code>.</p>`;
  } else {
    try { E.plantillasIds = (await pedir("api/categorias")).plantillas || null; } catch { /* opcional */ }
  }
  if (!E.corridas.length) {
    $("#lectura").innerHTML = `<p class="lectura-vacia">Todavía no hay lotes. Usá <b>Agregar lote</b> para clasificar algunos contactos.</p>`;
    return;
  }
  E.corrida = E.corridas[0].nombre;
  pintarCorridas();
  await cargarCorrida(E.corrida);
}

iniciar();
