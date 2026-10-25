/* Cloudflare Pages (modo avanzado). Dos trabajos:
   1) POST /api/cotizar: recibe el pedido del formulario y pide a Odoo (erp.gatheringsgt.com) que cree la cotización y se la
      envíe al cliente (addon odoo/addons/gatherings_cotizacion, método sale.order.gt_web_quote). Variables y secretos en Pages:
        ODOO_URL (https://erp.gatheringsgt.com), ODOO_DB, ODOO_USER, ODOO_API_KEY (secreto),
        CF_ACCESS_CLIENT_ID y CF_ACCESS_CLIENT_SECRET (secreto): Service Token de Cloudflare Access, porque Odoo está detrás de Access,
        TURNSTILE_SECRET (secreto, opcional): si existe, se exige el token de Cloudflare Turnstile.
      El navegador solo manda producto y cantidad: los precios y mínimos los pone Odoo.
   2) Vista previa por producto al compartir links.

   WhatsApp y Facebook no ejecutan JavaScript, así que para /?p=<id> y /m/?p=<id> cambiamos aquí las etiquetas
   og:* por las del producto. Cualquier otra ruta se sirve tal cual.
   Mantener PRODUCTS al día con assets/shared.js (nombre, precio, mínimo, unidad, descripción). */

const PRODUCTS = {
  "single": {name: "The Single", price: 150, desc: "Pequeña selección gourmet para disfrutar algo especial en cualquier momento."},
  "cozy": {name: "The Cozy", price: 260, desc: "Perfecta para compartir en pareja o grupo pequeño."},
  "homestyle": {name: "The Homestyle", price: 500, desc: "Hecha para reunir a la familia y los amigos alrededor de una mesa llena de sabores."},
  "gathering": {name: "The Gathering", price: 800, desc: "Abundante, artesanal y pensada para hacer extraordinarios los encuentros especiales."},
  "tailored": {name: "The Tailored", price: null, desc: "Una creación a tu medida, diseñada según tus gustos, tu ocasión y tu estilo."},
  "little-box": {name: "The Little Box", price: 65, min: 5, desc: "Pequeño detalle gourmet, cuidadosamente presentado y listo para disfrutar."},
  "celebration-box": {name: "The Celebration Box", price: 175, min: 5, desc: "Charcutería y vino en una presentación especial para sorprender, regalar y brindar."},
  "mini-dome": {name: "The Mini Dome", price: 30, min: 10, desc: "Una porción individual de charcutería, ideal para eventos, detalles corporativos y regalos especiales."},
  "big-dome": {name: "The Big Dome", price: 50, min: 10, desc: "Una presentación especial de charcutería con una delicada flor de salami, perfecta para eventos, celebraciones y regalos memorables."},
  "glass-dome": {name: "The Glass Dome", price: 75, min: 10, desc: "Una pequeña creación gourmet bajo una elegante cúpula de vidrio."},
  "grazing-table": {name: "The Grazing Table", price: 90, min: 20, unit: "persona", desc: "Una mesa de charcutería diseñada a tu medida, con una selección gourmet para convertir cualquier celebración en un encuentro extraordinario."},
  "experience": {name: "The Experience", price: 150, min: 5, desc: "Una experiencia para crear, compartir y disfrutar. Aprende a armar tu propia tabla de charcutería y celebra alrededor de algo delicioso, hecho por ustedes."}
};

/* ===== Cotizaciones: sitio -> Odoo ===== */
const API_COTIZAR = "/api/cotizar";
const MAX_BODY = 8192;
const CAMPOS_TEXTO = ["nombre", "correo", "telefono", "fecha", "horario", "dir", "mensaje", "notas"];
/* Anticipo mínimo de 12 horas desde el inicio del horario, en hora de Guatemala (UTC-6, sin cambio de hora); igual que en shared.js. */
const ANTICIPO_H = 12, GT_OFFSET_H = 6, SLOTS = { "Durante la mañana": 8, "Durante la tarde": 13 };
const slotOk = (fecha, horario, now = Date.now()) =>
  /^\d{4}-\d{2}-\d{2}$/.test(fecha) && Object.prototype.hasOwnProperty.call(SLOTS, horario) &&
  Date.parse(fecha + "T00:00:00Z") + (SLOTS[horario] + GT_OFFSET_H) * 36e5 - now >= ANTICIPO_H * 36e5;
let odooUid = null;   // se reutiliza mientras viva el aislamiento del Worker

const jsonRes = (obj, status = 200) => new Response(JSON.stringify(obj), {
  status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
});
/* Error que el sitio resuelve abriendo WhatsApp con el pedido: el cliente nunca se queda sin respuesta. */
const fallback = (msg, status = 502) => jsonRes({ ok: false, fallback: true, error: msg }, status);

async function turnstileOk(env, token, ip) {
  if (!env.TURNSTILE_SECRET) return true;
  if (!token) return false;
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", token);
  if (ip) form.append("remoteip", ip);
  try {
    const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
    return !!(await r.json()).success;
  } catch (e) {
    console.error("turnstile", e);
    return false;
  }
}

async function odooRpc(env, service, method, args) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 28000);   // Odoo genera el PDF y envía el correo antes de responder
  try {
    const r = await fetch(`${env.ODOO_URL}/jsonrpc`, {
      method: "POST", signal: ctl.signal,
      headers: {
        "content-type": "application/json",
        "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET
      },
      body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { service, method, args }, id: 1 })
    });
    if (!r.ok) throw new Error(`Odoo respondió HTTP ${r.status}`);
    const j = await r.json();
    if (j.error) throw new Error((j.error.data && j.error.data.message) || j.error.message || "error de Odoo");
    return j.result;
  } finally {
    clearTimeout(timer);
  }
}

async function cotizar(request, env) {
  const url = new URL(request.url);
  if (request.method !== "POST") return jsonRes({ ok: false, error: "Método no permitido." }, 405);
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== url.host) return jsonRes({ ok: false, error: "Origen no permitido." }, 403);

  const raw = await request.text();
  if (raw.length > MAX_BODY) return jsonRes({ ok: false, error: "Pedido demasiado grande." }, 413);
  let body;
  try { body = JSON.parse(raw); } catch (e) { return jsonRes({ ok: false, error: "Solicitud inválida." }, 400); }
  if (!body || typeof body !== "object" || !Array.isArray(body.items)) return jsonRes({ ok: false, error: "Solicitud inválida." }, 400);

  if (body.empresa) return jsonRes({ ok: true, estado: "revision", cotizacion: "" });   // campo trampa: un humano no lo llena
  if (!slotOk(String(body.fecha || "").trim(), String(body.horario || "").trim())) {
    return jsonRes({ ok: false, error: "Necesitamos al menos 12 horas de anticipación: elige otra fecha u horario." }, 400);
  }
  if (!(await turnstileOk(env, body.turnstile, request.headers.get("cf-connecting-ip")))) {
    return jsonRes({ ok: false, error: "No pudimos verificar que eres una persona. Recarga la página e inténtalo de nuevo." }, 400);
  }
  if (!env.ODOO_URL || !env.ODOO_API_KEY || !env.CF_ACCESS_CLIENT_ID || !env.CF_ACCESS_CLIENT_SECRET) {
    console.error("cotizar: faltan variables de Odoo");
    return fallback("Cotización automática no disponible.", 503);
  }

  const pedido = { items: body.items.slice(0, 20).map(i => ({ id: String(i && i.id), qty: Number(i && i.qty) })) };
  CAMPOS_TEXTO.forEach(k => { pedido[k] = typeof body[k] === "string" ? body[k].slice(0, 1000) : ""; });

  try {
    if (odooUid == null) {
      odooUid = await odooRpc(env, "common", "authenticate", [env.ODOO_DB, env.ODOO_USER, env.ODOO_API_KEY, {}]);
      if (!odooUid) throw new Error("Odoo rechazó el usuario o la llave API");
    }
    const r = await odooRpc(env, "object", "execute_kw", [env.ODOO_DB, odooUid, env.ODOO_API_KEY, "sale.order", "gt_web_quote", [pedido]]);
    if (!r || typeof r !== "object") throw new Error("respuesta inesperada de Odoo");
    if (!r.ok) return jsonRes({ ok: false, error: r.error || "Revisa los datos de tu pedido." }, 400);
    return jsonRes({ ok: true, estado: r.estado, cotizacion: r.cotizacion });
  } catch (e) {
    odooUid = null;   // por si la causa fue la autenticación; se reintenta en la próxima solicitud
    console.error("cotizar:", e && e.message);
    return fallback("No pudimos generar la cotización automática.");
  }
}

const PAGES = new Set(["/", "/index.html", "/m", "/m/", "/m/index.html"]);

const cleanDesc = (p) => {
  const precio = p.price == null ? "Precio según tu pedido" : `Q${p.price}${p.unit ? " por " + p.unit : p.min ? " c/u" : ""}`;
  const minimo = p.min ? ` · Pedido mínimo: ${p.min} ${p.unit ? p.unit + "s" : "unidades"}` : "";
  return `${precio}${minimo}. ${p.desc ? p.desc + " " : ""}Pedí por WhatsApp.`;
};

const setContent = (value) => ({ element: (el) => el.setAttribute("content", value) });

export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname === API_COTIZAR) return cotizar(request, env);
    const res = await env.ASSETS.fetch(request);
    const url = new URL(request.url);
    const id = url.searchParams.get("p");
    const product = id && Object.prototype.hasOwnProperty.call(PRODUCTS, id) ? PRODUCTS[id] : null;
    const type = res.headers.get("content-type") || "";
    if (request.method !== "GET" || !product || !PAGES.has(url.pathname) || !type.includes("text/html")) return res;

    const title = `${product.name} · Gatherings GT`;
    const desc = cleanDesc(product);
    const image = `${url.origin}/fotos/${id}/card.jpg`;
    const page = `${url.origin}/?p=${id}`;

    return new HTMLRewriter()
      .on("title", { element: (el) => el.setInnerContent(title) })
      .on('meta[name="description"]', setContent(desc))
      .on('meta[property="og:title"]', setContent(title))
      .on('meta[property="og:description"]', setContent(desc))
      .on('meta[property="og:image"]', setContent(image))
      .on("head", {
        element: (el) => el.append(
          `<meta property="og:url" content="${page}">` +
          '<meta property="og:image:width" content="900"><meta property="og:image:height" content="675">' +
          '<meta name="twitter:card" content="summary_large_image">',
          { html: true })
      })
      .transform(res);
  }
};
