/* Cloudflare Pages (modo avanzado): vista previa por producto al compartir links.
   WhatsApp y Facebook no ejecutan JavaScript, así que para /?p=<id> y /m/?p=<id> cambiamos aquí las etiquetas
   og:* por las del producto. Cualquier otra ruta se sirve tal cual.
   Mantener PRODUCTS al día con assets/shared.js (nombre, precio, mínimo, foto). */

const PRODUCTS = {
  "single":          {name: "The Single",          price: 150, desc: "Práctica, individual y lista para disfrutar. Cubre 1 persona."},
  "cozy":            {name: "The Cozy",            price: 260, desc: "Perfecta para compartir en pareja o grupo pequeño. Cubre de 2 a 3 personas."},
  "homestyle":       {name: "The Homestyle",       price: 500, desc: "Pensada para reuniones familiares o entre amigos. Cubre de 4 a 6 personas."},
  "gathering":       {name: "The Gathering",       price: 800, desc: "Abundante, para encuentros especiales. Cubre de 7 a 10 personas."},
  "little-box":      {name: "The Little Box",      price: 65,  min: 5},
  "celebration-box": {name: "The Celebration Box", price: 175, min: 5},
  "mini-dome":       {name: "The Mini Dome",       price: 30,  min: 10},
  "big-dome":        {name: "The Big Dome",        price: 50,  min: 10},
  "glass-dome":      {name: "The Glass Dome",      price: 75,  min: 10},
  "tailored":        {name: "The Tailored",        price: null, desc: "Hecha a la medida: ingredientes, cantidades y adaptaciones (sugar free, gluten free, entre otras)."}
};

const PAGES = new Set(["/", "/index.html", "/m", "/m/", "/m/index.html"]);

const cleanDesc = (p) => {
  const precio = p.price == null ? "Precio según tu pedido" : `Q${p.price}${p.min ? " c/u" : ""}`;
  const minimo = p.min ? ` · Pedido mínimo: ${p.min} unidades` : "";
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
