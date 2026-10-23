/* Cloudflare Pages (modo avanzado): vista previa por producto al compartir links.
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

const PAGES = new Set(["/", "/index.html", "/m", "/m/", "/m/index.html"]);

const cleanDesc = (p) => {
  const precio = p.price == null ? "Precio según tu pedido" : `Q${p.price}${p.unit ? " por " + p.unit : p.min ? " c/u" : ""}`;
  const minimo = p.min ? ` · Pedido mínimo: ${p.min} ${p.unit ? p.unit + "s" : "unidades"}` : "";
  return `${precio}${minimo}. ${p.desc ? p.desc + " " : ""}Pedí por WhatsApp.`;
};

const setContent = (value) => ({ element: (el) => el.setAttribute("content", value) });

export default {
  async fetch(request, env) {
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
