/* Gatherings GT · lógica compartida por la versión de escritorio (/) y móvil (/m/).
   Sin dependencias. Carrito guardado en el navegador y en el link (?pedido=). */

/* ===== CONFIGURACIÓN (editable) ===== */
const WA = "50255412293";          // +502 5541 2293
const CURRENCY = "Q";
const API_COTIZAR = "/api/cotizar";   // POST: Odoo crea la cotización y se la envía al cliente (ver _worker.js)
const TURNSTILE_KEY = "0x4AAAAAAFi5dZKAr9CTywNw";   // clave pública del widget Cloudflare Turnstile; vacío = sin verificación (el Worker la exige si tiene TURNSTILE_SECRET)
/* price: número en quetzales (precio final), o null para "Cotizar". min: pedido mínimo de unidades (opcional).
   rev: true = se cotiza a la medida o con precio por confirmar: la cotización pasa por revisión y no sale sola (debe coincidir con «Requiere revisión» en Odoo).
   photo: foto de la tarjeta, ruta desde la raíz del sitio; vacío = recuadro «Foto próximamente».
   gallery: fotos del detalle (la primera es la principal).  incl: «Qué incluye» (texto, o lista de viñetas; vacío = se confirma por WhatsApp).
   info: líneas «Tamaño», «Porciones» o «Presentación» ([[etiqueta, valor], ...]).  unit: unidad del precio si no es «c/u» (ej. "persona").  note: texto final del detalle. */
const pics = (id, n) => Array.from({length: n}, (_, i) => `fotos/${id}/${i + 1}.jpg`);
const PRODUCTS = [
  {id:"single", name:"The Single", desc:"Pequeña selección gourmet para disfrutar algo especial en cualquier momento.", price:150, photo:"fotos/single/card.jpg", gallery:pics("single",5),
   incl:"Uvas verdes sin semilla, quesos cheddar, suizo y pepper jack, dip de queso de cabra con frutos secos, salami imperial, salami español, miel, aceitunas, galletas multigrano, mini pretzels, dátiles y almendras cubiertas de chocolate.",
   info:[["Tamaño","10 × 15 cm"],["Porciones","1–2 personas"]]},
  {id:"cozy", name:"The Cozy", desc:"Perfecta para compartir en pareja o grupo pequeño.", price:260, photo:"fotos/cozy/card.jpg", gallery:pics("cozy",5),
   incl:"Uvas verdes sin semilla, fresas frescas, quesos cheddar, suizo y pepper jack, dip de queso de cabra con frutos secos, salami imperial, salami español, miel, aceitunas, galletas multigrano, mini pretzels, pan, dátiles y almendras cubiertas de chocolate.",
   info:[["Tamaño","20 × 30 cm"],["Porciones","2–3 personas"]]},
  {id:"homestyle", name:"The Homestyle", desc:"Hecha para reunir a la familia y los amigos alrededor de una mesa llena de sabores.", price:500, photo:"fotos/homestyle/card.jpg", gallery:pics("homestyle",5),
   incl:"Uvas verdes sin semilla, fresas frescas, quesos cheddar, suizo y pepper jack, dip de queso de cabra con frutos secos, salami imperial, salami español, jamón serrano, miel, aceitunas, galletas multigrano, mini pretzels, pan, dátiles y almendras cubiertas de chocolate.",
   info:[["Tamaño","20 × 60 cm"],["Porciones","4–6 personas"]]},
  {id:"gathering", name:"The Gathering", desc:"Abundante, artesanal y pensada para hacer extraordinarios los encuentros especiales.", price:800, photo:"fotos/gathering/card.jpg", gallery:pics("gathering",5),
   incl:"Uvas verdes sin semilla, fresas frescas, quesos cheddar, suizo y pepper jack, dip de queso de cabra con frutos secos, salami imperial, salami español, jamón serrano, miel, aceitunas, galletas multigrano, mini pretzels, pan, dátiles y almendras cubiertas de chocolate.",
   info:[["Tamaño","30 × 70 cm"],["Porciones","7–10 personas"]]},
  {id:"tailored", name:"The Tailored", desc:"Una creación a tu medida, diseñada según tus gustos, tu ocasión y tu estilo.", rev:true, price:null, photo:"fotos/tailored/card.jpg", gallery:pics("tailored",5),
   incl:"Una selección personalizada de quesos, charcutería, frutas frescas y acompañamientos gourmet, definida según tus preferencias, la ocasión y tu presupuesto. Cada creación se diseña a tu medida.",
   info:[]},
  {id:"little-box", name:"The Little Box", desc:"Pequeño detalle gourmet, cuidadosamente presentado y listo para disfrutar.", price:65, min:5, photo:"fotos/little-box/card.jpg", gallery:pics("little-box",2),
   incl:"Uvas verdes, queso cheddar, salami español, galletas multigrano, nueces naturales y almendras cubiertas de chocolate.",
   info:[["Presentación","cajita de cartón blanco de 10 × 10 cm con tapa transparente."]]},
  {id:"celebration-box", name:"The Celebration Box", desc:"Charcutería y vino en una presentación especial para sorprender, regalar y brindar.", price:175, min:5, photo:"fotos/celebration-box/card.jpg", gallery:pics("celebration-box",4),
   incl:"Una mini botella de vino tinto o rosado, acompañada de The Little Box con uvas verdes, queso cheddar, salami español, galletas multigrano, nueces naturales y almendras cubiertas de chocolate.",
   info:[["Presentación","caja de cartón blanco de 20 × 20 cm con ventana transparente."]]},
  {id:"mini-dome", name:"The Mini Dome", desc:"Una porción individual de charcutería, ideal para eventos, detalles corporativos y regalos especiales.", price:30, min:10, photo:"fotos/mini-dome/card.jpg", gallery:pics("mini-dome",2),
   incl:"Uvas verdes sin semilla, queso cheddar, salami español y fresa fresca.",
   info:[["Presentación","mini domo transparente de plástico."]]},
  {id:"big-dome", name:"The Big Dome", desc:"Una presentación especial de charcutería con una delicada flor de salami, perfecta para eventos, celebraciones y regalos memorables.", price:50, min:10, photo:"fotos/big-dome/card.jpg", gallery:pics("big-dome",3),
   incl:"Una flor de salami español, uvas verdes sin semilla, fresa fresca, quesos cheddar y pepper jack, y galletas multigrano.",
   info:[["Presentación","domo transparente de plástico."]]},
  {id:"glass-dome", name:"The Glass Dome", desc:"Una pequeña creación gourmet bajo una elegante cúpula de vidrio.", price:75, min:10, photo:"fotos/glass-dome/card.jpg", gallery:pics("glass-dome",2),
   incl:"Una flor de salami español, uvas verdes sin semilla, fresa fresca, queso cheddar y galletas multigrano.",
   info:[["Presentación","elegante domo de vidrio."]]},
  {id:"grazing-table", name:"The Grazing Table", desc:"Una mesa de charcutería diseñada a tu medida, con una selección gourmet para convertir cualquier celebración en un encuentro extraordinario.", rev:true, price:90, min:20, unit:"persona", photo:"fotos/grazing-table/card.jpg", gallery:pics("grazing-table",6),
   incl:["Mesa de charcutería con quesos, charcutería premium, frutas frescas y acompañamientos gourmet.","Selecciones y adicionales personalizados según tus preferencias y el estilo de tu evento.","Montaje y desmontaje de la mesa."],
   info:[]},
  {id:"experience", name:"The Experience", desc:"Una experiencia para crear, compartir y disfrutar. Aprende a armar tu propia tabla de charcutería y celebra alrededor de algo delicioso, hecho por ustedes.", rev:true, price:150, min:5, photo:"fotos/experience/card.jpg", gallery:pics("experience",8),
   incl:["Mínimo 5 unidades de The Single.","Una clase guiada de una hora para aprender a armar una tabla de charcutería, sin costo adicional.","Un momento para crear juntos y disfrutar de sus tablas mientras comparten."],
   info:[], note:"Ideal para cumpleaños, reuniones entre amigos, celebraciones especiales o simplemente para hacer algo diferente."},
  {id:"the-goat", name:"The GOAT", desc:"Nuestro famoso dip de queso de cabra con frutos secos. Cremoso, irresistible y, para muchos, el mejor de todos los tiempos. 💙", price:65, photo:"fotos/the-goat/card.jpg", gallery:pics("the-goat",1),
   incl:"Dip artesanal de queso de cabra (120 g), cubierto con nueces (30 g) y arándanos (30 g).",
   info:[["Peso neto total","180 g."]]},
  {id:"the-break", name:"The Break", desc:"Una pausa deliciosa para compartir y recargar energías. Meriendas prácticas, ricas y listas para disfrutar, ideales para reuniones, eventos y jornadas de trabajo.", rev:true, price:null, photo:"fotos/the-break/card.jpg", gallery:pics("the-break",2),
   incl:["Un panini preparado y listo para disfrutar.","Una selección de snacks para acompañar.","Una bebida.","Presentación individual, práctica y lista para entregar."],
   info:[["Precio","personalizado según la selección, la cantidad de meriendas y las necesidades de cada empresa."]]}
];
/* ===================================== */

const ROOT = document.documentElement.dataset.root || "";   // "" en /, "../" en /m/
const CART_KEY = "gt_cart", FORM_KEY = "gt_form";
const $ = s => document.querySelector(s);
const money = n => CURRENCY + n.toLocaleString("es-GT");
const wa = t => "https://wa.me/" + WA + (t ? "?text=" + encodeURIComponent(t) : "");
const store = {
  get(k){ try{ return JSON.parse(localStorage.getItem(k)); }catch(e){ return null; } },
  set(k,v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch(e){} }
};
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

/* Carrito: { id: cantidad }. Se lee del link (?pedido=cozy.2,single.1) o del navegador. */
const cart = {};
function cartFromParam(s){
  const o = {};
  (s || "").split(",").forEach(x => {
    const [id, n] = x.split(".");
    const p = PRODUCTS.find(q => q.id === id);
    if (p && +n > 0) o[id] = Math.max(p.min || 1, Math.min(99, +n | 0));
  });
  return o;
}
function cartToParam(){
  return Object.keys(cart).filter(id => cart[id] > 0).map(id => id + "." + cart[id]).join(",");
}
function pageUrl(params){
  const q = Object.keys(params).filter(k => params[k]).map(k => k + "=" + encodeURIComponent(params[k]).replace(/%2C/g, ",")).join("&");
  return location.origin + location.pathname + (q ? "?" + q : "");
}

const unitsTxt = (p, n) => n === 1 ? (p.unit ? "1 " + p.unit : "1 unidad") : n + (p.unit ? " " + p.unit + "s" : " unidades");
const priceTxt = p => p.price ? money(p.price) + (p.unit ? " por " + p.unit : p.min ? " c/u" : "") : "Precio según tu pedido";
const minTxt = p => p.min ? `<div class="minq">Pedido mínimo: ${unitsTxt(p, p.min)}</div>` : "";
const titleHtml = n => /^The /.test(n) ? `<span class="ttl"><span class="the" role="img" aria-label="The"></span><span>${esc(n.slice(4))}</span></span>` : esc(n);
const qtyHtml = p => `<div class="qty"><button type="button" data-chg="${p.id}" data-d="-1" aria-label="Quitar ${esc(p.name)}">−</button><span data-q="${p.id}">0</span><button type="button" data-chg="${p.id}" data-d="1" aria-label="Agregar ${esc(p.name)}">+</button>`;

function cardHtml(p){
  const img = p.photo
    ? `<img src="${ROOT}${esc(p.photo)}" alt="${esc(p.name)}" loading="lazy" decoding="async">`
    : `<div class="ph">Foto próximamente</div>`;
  return `<div class="card" id="p-${p.id}"><a class="pic" href="?p=${p.id}" data-open="${p.id}" aria-label="Ver detalle de ${esc(p.name)}">${img}</a>
<div class="b"><h3><a class="tl" href="?p=${p.id}" data-open="${p.id}">${titleHtml(p.name)}</a></h3><p>${esc(p.desc)}</p><div class="price">${priceTxt(p)}</div>${minTxt(p)}
<a class="more" href="?p=${p.id}" data-open="${p.id}">Ver detalle y fotos</a>
${qtyHtml(p)}<button type="button" class="lnk" data-link="${p.id}">Copiar link</button></div></div></div>`;
}

/* Detalle de producto: ventana sobre el menú, con galería. Abre con ?p=id (link directo). */
let detailId = null, lastFocus = null;
function detailHtml(p){
  const g = p.gallery || [];
  const gal = g.length
    ? `<div class="gal" id="gal">${g.map((f, i) => `<img src="${ROOT}${esc(f)}" alt="${esc(p.name)} (foto ${i + 1} de ${g.length})" ${i ? 'loading="lazy"' : ""} decoding="async">`).join("")}</div>
${g.length > 1 ? `<button type="button" class="nav prev" data-gal="-1" aria-label="Foto anterior">‹</button><button type="button" class="nav next" data-gal="1" aria-label="Foto siguiente">›</button>
<div class="thumbs" id="thumbs">${g.map((f, i) => `<button type="button" data-th="${i}" aria-label="Ver foto ${i + 1}"><img src="${ROOT}${esc(f)}" alt="" loading="lazy"></button>`).join("")}</div>` : ""}`
    : `<div class="gal ph0"><div class="ph">Foto próximamente</div></div>`;
  const incl = Array.isArray(p.incl) && p.incl.length
    ? `<ul>${p.incl.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`
    : p.incl ? `<p>${esc(p.incl)}</p>`
    : `<p class="mut">El detalle de lo que incluye lo confirmamos por chat.</p>`;
  const info = (p.info || []).length ? `<p class="spec">${p.info.map(([k, v]) => `<b>${esc(k)}:</b> ${esc(v)}`).join("<br>")}</p>` : "";
  return `<div class="dlg" role="dialog" aria-modal="true" aria-labelledby="dt"><button type="button" class="x" data-close aria-label="Cerrar">×</button>
<div class="dg">${gal}</div>
<div class="di"><h2 id="dt">${titleHtml(p.name)}</h2><div class="price">${priceTxt(p)}</div>${minTxt(p)}<p>${esc(p.desc)}</p>
<h3>Qué incluye</h3>${incl}${info}${p.note ? `<p>${esc(p.note)}</p>` : ""}
${qtyHtml(p)}<button type="button" class="lnk" data-link="${p.id}">Copiar link</button></div>
<a class="btn btn-line2" target="_blank" rel="noopener" href="${wa("Hola Gatherings, quisiera información sobre " + p.name + ".")}">Preguntar por este producto</a>
<a class="btn btn-wa" href="#pedido" data-close>Ir a mi pedido</a></div></div>`;
}

function setGal(i){
  const g = $("#gal"); if (!g) return;
  const n = g.children.length, k = Math.max(0, Math.min(n - 1, i));
  g.scrollTo({left: k * g.clientWidth, behavior: "smooth"});
}
function markThumb(){
  const g = $("#gal"), t = $("#thumbs"); if (!g || !t) return;
  const k = Math.round(g.scrollLeft / (g.clientWidth || 1));
  [...t.children].forEach((b, j) => b.classList.toggle("on", j === k));
}

function openDetail(id, push){
  const p = PRODUCTS.find(x => x.id === id), box = $("#detail"); if (!p || !box) return;
  if (detailId === null) lastFocus = document.activeElement;
  detailId = id;
  box.innerHTML = detailHtml(p);
  box.hidden = false; document.body.classList.add("noscroll");
  const g = $("#gal"); if (g){ g.addEventListener("scroll", markThumb, {passive:true}); markThumb(); }
  render();
  const x = box.querySelector(".x"); if (x) x.focus();
  if (push) history.pushState({d:id}, "", pageUrl({p:id}));
}
function closeDetail(fromPop){
  const box = $("#detail"); if (!box || detailId === null) return;
  detailId = null; box.hidden = true; box.innerHTML = ""; document.body.classList.remove("noscroll");
  if (!fromPop) { if (history.state && history.state.d) history.back(); else history.replaceState(null, "", pageUrl({})); }
  if (lastFocus && lastFocus.focus) lastFocus.focus();
}

function lines(){ return PRODUCTS.filter(p => cart[p.id]).map(p => ({p, n: cart[p.id]})); }

/* Productos del pedido que Andrea cotiza a mano: el pedido completo pasa por revisión y la cotización llega después. */
const revNames = L => L.filter(x => x.p.rev).map(x => x.p.name);
const revList = ns => ns.length > 1 ? ns.slice(0, -1).join(", ") + " y " + ns[ns.length - 1] : ns[0];
const revMsg = ns => `Tu pedido incluye ${revList(ns)}, que ${ns.length > 1 ? "se cotizan" : "se cotiza"} a la medida o con precio por confirmar. Te enviaremos la cotización completa por correo después de revisarla, no al instante.`;

function render(){
  const L = lines(), n = L.reduce((a,x) => a + (x.p.unit ? 1 : x.n), 0);   /* por persona = 1 producto */
  const known = L.length && L.every(x => x.p.price), tot = L.reduce((a,x) => a + (x.p.price||0) * x.n, 0);
  document.querySelectorAll("[data-q]").forEach(e => { e.textContent = cart[e.dataset.q] || 0; });
  $("#cart").classList.toggle("on", n > 0);
  $("#cartTxt").textContent = n + (n === 1 ? " producto" : " productos") + (known && tot ? " · " + money(tot) : "");
  $("#sum").innerHTML = n ? L.map(x => `${x.p.unit ? unitsTxt(x.p, x.n) : x.n} × ${esc(x.p.name)}`).join("<br>") : "Aún no has agregado nada. También puedes escribirnos directo para cotizar un evento.";
  $("#saveBox").hidden = !n;
  const rn = $("#revNote"), rv = revNames(L);
  if (rn){ rn.hidden = !rv.length; rn.textContent = rv.length ? revMsg(rv) : ""; }
}

function change(id, d){
  const p = PRODUCTS.find(x => x.id === id), min = (p && p.min) || 1, cur = cart[id] || 0;
  /* con pedido mínimo: «+» desde 0 salta al mínimo y «−» desde el mínimo vuelve a 0 */
  let n = cur + d;
  if (d > 0 && n < min) n = min;
  if (d < 0 && n < min) n = 0;
  cart[id] = Math.max(0, Math.min(99, n));
  store.set(CART_KEY, cart);
  render();
}

function toast(msg){
  const t = $("#toast"); t.textContent = msg; t.classList.add("on");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("on"), 2200);
}
function copy(text, okMsg){
  const done = () => toast(okMsg);
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, () => prompt("Copiá este link:", text));
  else prompt("Copiá este link:", text);
}

function waText(f, L){
  const items = L.length ? L.map(x => `• ${x.p.unit ? unitsTxt(x.p, x.n) : x.n} × ${x.p.name}${x.p.price ? " (" + money(x.p.price * x.n) + ")" : " (precio por confirmar)"}`).join("\n") : "• (sin productos: quiero cotizar)";
  const tot = L.length && L.every(x => x.p.price) ? "\nSubtotal tablas: " + money(L.reduce((a,x) => a + x.p.price * x.n, 0)) + " (envío aparte, según tu ubicación)" : "";
  return `Hola Gatherings, quiero hacer un pedido:\n${items}${tot}\n\nNombre: ${f.get("nombre")}\nFecha: ${f.get("fecha")}\nHorario de entrega: ${f.get("horario")}\nDirección: ${f.get("dir") || "-"}\nMensaje personalizado: ${f.get("mensaje") || "-"}\nNotas: ${f.get("notas") || "-"}`;
}

/* Cloudflare Turnstile (anti-bots): se carga al tocar el formulario, no al abrir la página. */
let tsToken = "", tsWidget = null;
function loadTurnstile(){
  if (!TURNSTILE_KEY || document.getElementById("tsScript")) return;
  const s = document.createElement("script");
  s.id = "tsScript"; s.async = true; s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
  s.onload = () => { tsWidget = window.turnstile.render("#ts", {sitekey: TURNSTILE_KEY, callback: t => { tsToken = t; }, "expired-callback": () => { tsToken = ""; }, "error-callback": () => { tsToken = ""; }}); };
  document.head.appendChild(s);
}

function say(text, cls, waLink){
  const m = $("#qmsg"); m.className = "qmsg" + (cls ? " " + cls : ""); m.textContent = text;
  if (waLink){ m.appendChild(document.createTextNode(" ")); const a = document.createElement("a"); a.href = waLink; a.target = "_blank"; a.rel = "noopener"; a.textContent = "Continuar por WhatsApp"; m.appendChild(a); }
}

/* «Recibir cotización por correo»: el pedido va a Odoo, que arma la cotización con los precios oficiales y la envía. */
async function quote(f, L){
  const btns = document.querySelectorAll("#f button[type=submit]"), correo = (f.get("correo") || "").trim();
  if (!L.length) return say("Agrega al menos un producto para recibir tu cotización por correo. Para un evento a la medida, escríbenos por WhatsApp.", "err");
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)){ $("#f").elements.correo.focus(); return say("Escribe un correo válido para enviarte la cotización.", "err"); }
  if (TURNSTILE_KEY && !tsToken){ loadTurnstile(); return say("Un momento: estamos verificando que eres una persona. Vuelve a pulsar el botón en unos segundos o, si no avanza,", "", wa(waText(f, L))); }
  const body = {items: L.map(x => ({id: x.p.id, qty: x.n})), turnstile: tsToken, empresa: f.get("empresa") || ""};
  ["nombre","correo","telefono","fecha","horario","dir","mensaje","notas"].forEach(k => { body[k] = (f.get(k) || "").trim(); });
  btns.forEach(b => { b.disabled = true; });
  say("Preparando tu cotización…");
  const rv = revNames(L);
  const alWa = () => say("No pudimos generar la cotización automática en este momento.", "err", wa(waText(f, L)));
  try {
    const r = await fetch(API_COTIZAR, {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body)});
    const j = await r.json().catch(() => ({}));
    if (j.ok){
      say(j.estado === "enviada"
        ? `¡Listo! Te enviamos la cotización a ${correo}. Si no la ves, revisa tu carpeta de spam o promociones.`
        : `Recibimos tu solicitud.${rv.length ? ` ${revList(rv)} ${rv.length > 1 ? "requieren" : "requiere"} revisión: ` : " "}Te enviaremos la cotización completa a ${correo} en breve.`, "");
      Object.keys(cart).forEach(k => delete cart[k]); store.set(CART_KEY, cart); render();
    } else if (j.fallback || !r.ok && !j.error) alWa();
    else say(j.error || "Revisa los datos de tu pedido.", "err");
  } catch (e) { alWa(); }
  finally {
    btns.forEach(b => { b.disabled = false; });
    tsToken = ""; if (tsWidget !== null && window.turnstile) window.turnstile.reset(tsWidget);
  }
}

/* Anticipo mínimo: cada horario cuenta desde su hora de inicio (hora de Guatemala, UTC-6 sin cambio de hora). */
const GT_OFFSET_H = 6, ANTICIPO_H = 12, SLOTS = {"Durante la mañana": 8, "Durante la tarde": 13};
const isoDay = ms => new Date(ms).toISOString().slice(0, 10);
function slotOk(fecha, horario, now = Date.now()){
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha || "") || !Object.prototype.hasOwnProperty.call(SLOTS, horario)) return false;
  const h = SLOTS[horario];
  return Date.parse(fecha + "T00:00:00Z") + (h + GT_OFFSET_H) * 36e5 - now >= ANTICIPO_H * 36e5;
}
/* Primer día con algún horario disponible y habilitación de horarios según la fecha elegida. */
function refreshSlots(){
  const form = $("#f"), fecha = form.elements.fecha, sel = form.elements.horario, now = Date.now();
  let d = now - GT_OFFSET_H * 36e5;
  while (!Object.keys(SLOTS).some(h => slotOk(isoDay(d), h, now))) d += 864e5;
  fecha.min = isoDay(d);
  [...sel.options].filter(o => o.value).forEach(o => {
    o.disabled = !!fecha.value && !slotOk(fecha.value, o.value, now);
    o.textContent = o.value + (o.disabled ? " (no disponible)" : "");
  });
  if (sel.selectedOptions[0] && sel.selectedOptions[0].disabled) sel.value = "";
}

function send(e){
  e.preventDefault();
  const f = new FormData($("#f")), L = lines();
  refreshSlots();
  if (!slotOk(f.get("fecha"), f.get("horario"))){
    $("#f").elements.fecha.focus(); say("Necesitamos al menos 12 horas de anticipación: elige otra fecha u horario.", "err");
    return false;
  }
  if (e.submitter && e.submitter.dataset.via === "quote"){ quote(f, L); return false; }
  window.open(wa(waText(f, L)), "_blank", "noopener");
  return false;
}

function init(){
  const params = new URLSearchParams(location.search);
  $("#grid").innerHTML = PRODUCTS.map(cardHtml).join("");
  const box = document.createElement("div"); box.id = "detail"; box.className = "detail"; box.hidden = true; document.body.appendChild(box);
  ["waTop","waFoot","fab"].forEach(i => { const e = $("#" + i); if (e) e.href = wa("Hola Gatherings, quisiera información sobre sus tablas."); });

  /* carrito: el link (?pedido=) manda sobre lo guardado */
  const fromUrl = cartFromParam(params.get("pedido"));
  Object.assign(cart, Object.keys(fromUrl).length ? fromUrl : (store.get(CART_KEY) || {}));
  PRODUCTS.forEach(p => { if (p.min && cart[p.id] > 0 && cart[p.id] < p.min) cart[p.id] = p.min; });
  store.set(CART_KEY, cart);

  /* borrador del formulario */
  const draft = store.get(FORM_KEY) || {}, form = $("#f");
  Object.keys(draft).forEach(k => { if (form.elements[k] && form.elements[k].type !== "date") form.elements[k].value = draft[k]; });
  form.addEventListener("input", () => {
    const d = {};
    new FormData(form).forEach((v,k) => { d[k] = v; });
    store.set(FORM_KEY, d);
  });
  [...form.elements.horario.options].forEach(o => { if (!o.hasAttribute("value")) o.value = o.text; });   /* el texto cambia a «no disponible»; el valor no */
  refreshSlots();
  form.elements.fecha.addEventListener("change", refreshSlots);
  form.addEventListener("focusin", refreshSlots);
  form.addEventListener("submit", send);
  /* «Finalizar pedido» (barra inferior) hace lo mismo que el botón verde del formulario (también «Finalizar pedido»): valida y lleva al primer campo faltante */
  $("#finish").addEventListener("click", () => form.requestSubmit(form.querySelector("[data-via=wa]")));
  form.addEventListener("focusin", loadTurnstile, {once: true});

  document.addEventListener("click", ev => {
    const o = ev.target.closest("[data-open]");
    if (o){ ev.preventDefault(); openDetail(o.dataset.open, true); return; }
    const c = ev.target.closest("[data-close]");
    if (ev.target === box || c){
      if (c && c.tagName === "A"){ ev.preventDefault(); closeDetail(); const t = $("#pedido"); if (t) t.scrollIntoView({behavior:"smooth"}); }
      else closeDetail();
      return;
    }
    const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.gal){ const g = $("#gal"); if (g) setGal(Math.round(g.scrollLeft / g.clientWidth) + +b.dataset.gal); return; }
    if (b.dataset.th){ setGal(+b.dataset.th); return; }
    if (b.dataset.chg) change(b.dataset.chg, +b.dataset.d);
    else if (b.dataset.link) copy(pageUrl({p: b.dataset.link}), "Link del producto copiado");
    else if (b.id === "saveLink") copy(pageUrl({pedido: cartToParam()}), "Link de tu pedido copiado: abrilo en cualquier dispositivo para continuar");
    else if (b.id === "clearCart"){ Object.keys(cart).forEach(k => delete cart[k]); store.set(CART_KEY, cart); render(); }
  });

  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape" && detailId !== null) closeDetail();
    else if (ev.key === "ArrowRight" && detailId !== null) setGal(Math.round($("#gal").scrollLeft / $("#gal").clientWidth) + 1);
    else if (ev.key === "ArrowLeft" && detailId !== null) setGal(Math.round($("#gal").scrollLeft / $("#gal").clientWidth) - 1);
  });
  window.addEventListener("popstate", () => {
    const id = new URLSearchParams(location.search).get("p");
    if (id) openDetail(id, false); else closeDetail(true);
  });

  render();
  if (params.get("p")) openDetail(params.get("p"), false);
  else if (params.get("pedido")) { const e = $("#pedido"); if (e) setTimeout(() => e.scrollIntoView({behavior:"smooth"}), 50); }
}
init();
