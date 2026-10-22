/* Gatherings GT · lógica compartida por la versión de escritorio (/) y móvil (/m/).
   Sin dependencias. Carrito guardado en el navegador y en el link (?pedido=). */

/* ===== CONFIGURACIÓN (editable) ===== */
const WA = "50255412293";          // +502 5541 2293
const CURRENCY = "Q";
/* price: número en quetzales, o null para "Cotizar".
   photo: foto de la tarjeta, ruta desde la raíz del sitio; vacío = recuadro «Foto próximamente».
   gallery: fotos del detalle (la primera es la principal).  incl: lista «Qué incluye» (vacía = se confirma por WhatsApp). */
const pics = (id, n) => Array.from({length: n}, (_, i) => `fotos/${id}/${i + 1}.jpg`);
const PENDING = "Descripción y precio próximamente. Escribinos por chat para cotizar.";
const PRODUCTS = [
  {id:"single",    name:"The Single",    desc:"Práctica, individual y lista para disfrutar. Cubre 1 persona.",                         price:50,   photo:"fotos/single/card.jpg",    gallery:pics("single",4),    incl:[]},
  {id:"cozy",      name:"The Cozy",      desc:"Perfecta para compartir en pareja o grupo pequeño. Cubre de 2 a 3 personas.",             price:250,  photo:"fotos/cozy/card.jpg",      gallery:pics("cozy",5),      incl:[]},
  {id:"homestyle", name:"The Homestyle", desc:"Pensada para reuniones familiares o entre amigos. Cubre de 4 a 6 personas.",               price:450,  photo:"fotos/homestyle/card.jpg", gallery:pics("homestyle",5), incl:[]},
  {id:"gathering", name:"The Gathering", desc:"Abundante, para encuentros especiales. Cubre de 7 a 10 personas.",                         price:700,  photo:"fotos/gathering/card.jpg", gallery:pics("gathering",5), incl:[]},
  {id:"little-box",      name:"The Little Box",      desc:PENDING, price:null, photo:"fotos/little-box/card.jpg",      gallery:pics("little-box",3),      incl:[]},
  {id:"celebration-box", name:"The Celebration Box", desc:PENDING, price:null, photo:"fotos/celebration-box/card.jpg", gallery:pics("celebration-box",4), incl:[]},
  {id:"mini-dome",       name:"The Mini Dome",       desc:PENDING, price:null, photo:"fotos/mini-dome/card.jpg",       gallery:pics("mini-dome",2),       incl:[]},
  {id:"big-dome",        name:"The Big Dome",        desc:PENDING, price:null, photo:"fotos/big-dome/card.jpg",        gallery:pics("big-dome",3),        incl:[]},
  {id:"glass-dome",      name:"The Glass Dome",      desc:PENDING, price:null, photo:"fotos/glass-dome/card.jpg",      gallery:pics("glass-dome",4),      incl:[]},
  {id:"tailored",  name:"The Tailored",  desc:"Hecha a la medida: ingredientes, cantidades y adaptaciones (sugar free, gluten free, entre otras). El precio varía.", price:null, photo:"", gallery:[], incl:[]}
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
    if (PRODUCTS.some(p => p.id === id) && +n > 0) o[id] = Math.min(99, +n | 0);
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

const priceTxt = p => p.price ? money(p.price) : "Precio según tu pedido";
const titleHtml = n => /^The /.test(n) ? `<span class="ttl"><span class="the" role="img" aria-label="The"></span><span>${esc(n.slice(4))}</span></span>` : esc(n);
const qtyHtml = p => `<div class="qty"><button type="button" data-chg="${p.id}" data-d="-1" aria-label="Quitar ${esc(p.name)}">−</button><span data-q="${p.id}">0</span><button type="button" data-chg="${p.id}" data-d="1" aria-label="Agregar ${esc(p.name)}">+</button>`;

function cardHtml(p){
  const img = p.photo
    ? `<img src="${ROOT}${esc(p.photo)}" alt="${esc(p.name)}" loading="lazy" decoding="async">`
    : `<div class="ph">Foto próximamente</div>`;
  return `<div class="card" id="p-${p.id}"><a class="pic" href="?p=${p.id}" data-open="${p.id}" aria-label="Ver detalle de ${esc(p.name)}">${img}</a>
<div class="b"><h3><a class="tl" href="?p=${p.id}" data-open="${p.id}">${titleHtml(p.name)}</a></h3><p>${esc(p.desc)}</p><div class="price">${priceTxt(p)}</div>
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
  const incl = p.incl && p.incl.length
    ? `<ul>${p.incl.map(x => `<li>${esc(x)}</li>`).join("")}</ul>`
    : `<p class="mut">El detalle de lo que incluye lo confirmamos por chat.</p>`;
  return `<div class="dlg" role="dialog" aria-modal="true" aria-labelledby="dt"><button type="button" class="x" data-close aria-label="Cerrar">×</button>
<div class="dg">${gal}</div>
<div class="di"><h2 id="dt">${titleHtml(p.name)}</h2><div class="price">${priceTxt(p)}</div><p>${esc(p.desc)}</p>
<h3>Qué incluye</h3>${incl}
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

function render(){
  const L = lines(), n = L.reduce((a,x) => a + x.n, 0);
  const known = L.length && L.every(x => x.p.price), tot = L.reduce((a,x) => a + (x.p.price||0) * x.n, 0);
  document.querySelectorAll("[data-q]").forEach(e => { e.textContent = cart[e.dataset.q] || 0; });
  $("#cart").classList.toggle("on", n > 0);
  $("#cartTxt").textContent = n + (n === 1 ? " producto" : " productos") + (known && tot ? " · " + money(tot) : "");
  $("#sum").innerHTML = n ? L.map(x => `${x.n} × ${esc(x.p.name)}`).join("<br>") : "Aún no has agregado nada. También puedes escribirnos directo para cotizar un evento.";
  $("#saveBox").hidden = !n;
}

function change(id, d){
  cart[id] = Math.max(0, Math.min(99, (cart[id] || 0) + d));
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

function send(e){
  e.preventDefault();
  const f = new FormData($("#f")), L = lines();
  const items = L.length ? L.map(x => `• ${x.n} × ${x.p.name}${x.p.price ? " (" + money(x.p.price * x.n) + ")" : " (precio por confirmar)"}`).join("\n") : "• (sin productos: quiero cotizar)";
  const tot = L.length && L.every(x => x.p.price) ? "\nSubtotal tablas: " + money(L.reduce((a,x) => a + x.p.price * x.n, 0)) + " (envío aparte, Q35–Q45)" : "";
  const t = `Hola Gatherings, quiero hacer un pedido:\n${items}${tot}\n\nNombre: ${f.get("nombre")}\nFecha: ${f.get("fecha")}\nHorario de entrega: ${f.get("horario")}\nDirección: ${f.get("dir") || "-"}\nMensaje personalizado: ${f.get("mensaje") || "-"}\nNotas: ${f.get("notas") || "-"}`;
  window.open(wa(t), "_blank", "noopener");
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
  store.set(CART_KEY, cart);

  /* borrador del formulario */
  const draft = store.get(FORM_KEY) || {}, form = $("#f");
  Object.keys(draft).forEach(k => { if (form.elements[k] && form.elements[k].type !== "date") form.elements[k].value = draft[k]; });
  form.addEventListener("input", () => {
    const d = {};
    new FormData(form).forEach((v,k) => { d[k] = v; });
    store.set(FORM_KEY, d);
  });
  form.addEventListener("submit", send);

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
