/* Gatherings GT · lógica compartida por la versión de escritorio (/) y móvil (/m/).
   Sin dependencias. Carrito guardado en el navegador y en el link (?pedido=). */

/* ===== CONFIGURACIÓN (editable) ===== */
const WA = "50255412293";          // +502 5541 2293
const CURRENCY = "Q";
/* price: número en quetzales, o null para "Cotizar".  photo: ruta desde la raíz del sitio (ej. "fotos/cozy.jpg"); vacío = recuadro. */
const PRODUCTS = [
  {id:"single",    name:"The Single",    desc:"Práctica, individual y lista para disfrutar. Cubre 1 persona.",                         price:50,   photo:""},
  {id:"cozy",      name:"The Cozy",      desc:"Perfecta para compartir en pareja o grupo pequeño. Cubre de 2 a 3 personas.",             price:250,  photo:""},
  {id:"homestyle", name:"The Homestyle", desc:"Pensada para reuniones familiares o entre amigos. Cubre de 4 a 6 personas.",               price:450,  photo:""},
  {id:"gathering", name:"The Gathering", desc:"Abundante, para encuentros especiales. Cubre de 7 a 10 personas.",                         price:700,  photo:""},
  {id:"tailored",  name:"The Tailored",  desc:"Hecha a la medida: ingredientes, cantidades y adaptaciones (sugar free, gluten free, entre otras). El precio varía.", price:null, photo:""}
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

function cardHtml(p){
  const img = p.photo
    ? `<img src="${ROOT}${esc(p.photo)}" alt="${esc(p.name)}" loading="lazy" decoding="async">`
    : `<div class="ph">Foto próximamente</div>`;
  return `<div class="card" id="p-${p.id}">${img}
<div class="b"><h3>${esc(p.name)}</h3><p>${esc(p.desc)}</p><div class="price">${p.price ? money(p.price) : "Precio según tu pedido"}</div>
<div class="qty"><button type="button" data-chg="${p.id}" data-d="-1" aria-label="Quitar ${esc(p.name)}">−</button><span id="q-${p.id}">0</span><button type="button" data-chg="${p.id}" data-d="1" aria-label="Agregar ${esc(p.name)}">+</button>
<button type="button" class="lnk" data-link="${p.id}">Copiar link</button></div></div></div>`;
}

function lines(){ return PRODUCTS.filter(p => cart[p.id]).map(p => ({p, n: cart[p.id]})); }

function render(){
  const L = lines(), n = L.reduce((a,x) => a + x.n, 0);
  const known = L.length && L.every(x => x.p.price), tot = L.reduce((a,x) => a + (x.p.price||0) * x.n, 0);
  PRODUCTS.forEach(p => { const e = $("#q-" + p.id); if (e) e.textContent = cart[p.id] || 0; });
  $("#cart").classList.toggle("on", n > 0);
  $("#cartTxt").textContent = n + (n === 1 ? " producto" : " productos") + (known && tot ? " · " + money(tot) : "");
  $("#sum").innerHTML = n ? L.map(x => `${x.n} × ${esc(x.p.name)}`).join("<br>") : "Aún no agregaste nada. También podés escribirnos directo para cotizar un evento.";
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

function highlight(id){
  const e = document.getElementById("p-" + id);
  if (!e) return;
  e.classList.add("hl");
  setTimeout(() => e.scrollIntoView({block:"center", behavior:"smooth"}), 50);
}

function send(e){
  e.preventDefault();
  const f = new FormData($("#f")), L = lines();
  const items = L.length ? L.map(x => `• ${x.n} × ${x.p.name}${x.p.price ? " (" + money(x.p.price * x.n) + ")" : " (precio por confirmar)"}`).join("\n") : "• (sin productos: quiero cotizar)";
  const tot = L.length && L.every(x => x.p.price) ? "\nSubtotal tablas: " + money(L.reduce((a,x) => a + x.p.price * x.n, 0)) + " (envío aparte, Q35–Q45)" : "";
  const t = `Hola Gatherings, quiero hacer un pedido:\n${items}${tot}\n\nNombre: ${f.get("nombre")}\nFecha: ${f.get("fecha")}${f.get("hora") ? " " + f.get("hora") : ""}\nEntrega: ${f.get("entrega")}\nDirección: ${f.get("dir") || "-"}\nNotas: ${f.get("notas") || "-"}`;
  window.open(wa(t), "_blank", "noopener");
  return false;
}

function init(){
  const params = new URLSearchParams(location.search);
  $("#grid").innerHTML = PRODUCTS.map(cardHtml).join("");
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
    const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.chg) change(b.dataset.chg, +b.dataset.d);
    else if (b.dataset.link) copy(pageUrl({p: b.dataset.link}), "Link del producto copiado");
    else if (b.id === "saveLink") copy(pageUrl({pedido: cartToParam()}), "Link de tu pedido copiado: abrilo en cualquier dispositivo para continuar");
    else if (b.id === "clearCart"){ Object.keys(cart).forEach(k => delete cart[k]); store.set(CART_KEY, cart); render(); }
  });

  render();
  if (params.get("p")) highlight(params.get("p"));
  else if (params.get("pedido")) { const e = $("#pedido"); if (e) setTimeout(() => e.scrollIntoView({behavior:"smooth"}), 50); }
}
init();
