// node --test tests/site   (Node 20+). Prueba POST /api/cotizar de gatheringsgt/_worker.js con Odoo y Turnstile simulados.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../../gatheringsgt/_worker.js", import.meta.url), "utf8");
const worker = (await import("data:text/javascript;base64," + Buffer.from(src).toString("base64"))).default;

const ENV = {
  ODOO_URL: "https://erp.example", ODOO_DB: "gatherings", ODOO_USER: "web", ODOO_API_KEY: "key",
  CF_ACCESS_CLIENT_ID: "id.access", CF_ACCESS_CLIENT_SECRET: "secret",
  ASSETS: { fetch: async () => new Response("<html></html>", { headers: { "content-type": "text/html" } }) }
};
const PEDIDO = { nombre: "Ana Pérez", correo: "ana@example.com", telefono: "55551234", fecha: "2030-01-01", horario: "Durante la tarde",
  dir: "Zona 10", mensaje: "", notas: "", items: [{ id: "single", qty: 2, price: 1 }] };

function post(body, { origin = "https://gatheringsgt.com", env = ENV } = {}) {
  const req = new Request("https://gatheringsgt.com/api/cotizar", {
    method: "POST", headers: { "content-type": "application/json", origin }, body: typeof body === "string" ? body : JSON.stringify(body)
  });
  return worker.fetch(req, env);
}

function fakeOdoo(handler) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    const call = { url: String(url), headers: init.headers, body: init.body };
    calls.push(call);
    return handler(call);
  };
  return calls;
}
const rpc = result => new Response(JSON.stringify({ jsonrpc: "2.0", id: 1, result }), { status: 200 });

test("crea la cotización en Odoo con el Service Token y solo producto y cantidad", async () => {
  const calls = fakeOdoo(c => rpc(JSON.parse(c.body).params.method === "authenticate" ? 7 : { ok: true, estado: "enviada", cotizacion: "S00050", total: 300 }));
  const res = await post(PEDIDO);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true, estado: "enviada", cotizacion: "S00050" });
  assert.equal(calls[0].url, "https://erp.example/jsonrpc");
  assert.equal(calls[0].headers["CF-Access-Client-Id"], "id.access");
  assert.equal(calls[0].headers["CF-Access-Client-Secret"], "secret");
  const enviado = JSON.parse(calls.at(-1).body).params.args;
  assert.deepEqual(enviado.slice(0, 5), ["gatherings", 7, "key", "sale.order", "gt_web_quote"]);
  assert.equal(enviado[5][0].correo, "ana@example.com");
});

test("error de validación de Odoo se devuelve como 400 con mensaje para el cliente", async () => {
  fakeOdoo(c => rpc(JSON.parse(c.body).params.method === "authenticate" ? 7 : { ok: false, error: "Escribe un correo válido." }));
  const res = await post(PEDIDO);
  assert.equal(res.status, 400);
  assert.deepEqual(await res.json(), { ok: false, error: "Escribe un correo válido." });
});

test("si Odoo no responde, el sitio recibe fallback (para abrir WhatsApp)", async () => {
  fakeOdoo(() => { throw new Error("caído"); });
  const res = await post(PEDIDO);
  assert.equal(res.status, 502);
  assert.equal((await res.json()).fallback, true);
});

test("si Access rechaza el token (HTTP 403) también es fallback", async () => {
  fakeOdoo(() => new Response("login", { status: 403 }));
  const res = await post(PEDIDO);
  assert.equal(res.status, 502);
});

test("sin configuración de Odoo: 503 con fallback y sin llamar a Odoo", async () => {
  const calls = fakeOdoo(() => rpc(1));
  const res = await post(PEDIDO, { env: { ...ENV, ODOO_API_KEY: "" } });
  assert.equal(res.status, 503);
  assert.equal(calls.length, 0);
});

test("rechaza otro origen, método y cuerpos inválidos o enormes", async () => {
  const calls = fakeOdoo(() => rpc(1));
  assert.equal((await post(PEDIDO, { origin: "https://malo.example" })).status, 403);
  assert.equal((await post("no es json")).status, 400);
  assert.equal((await post({ nombre: "x" })).status, 400);
  assert.equal((await post({ ...PEDIDO, notas: "x".repeat(9000) })).status, 413);
  const get = await worker.fetch(new Request("https://gatheringsgt.com/api/cotizar"), ENV);
  assert.equal(get.status, 405);
  assert.equal(calls.length, 0);
});

test("el campo trampa responde como éxito sin llamar a Odoo", async () => {
  const calls = fakeOdoo(() => rpc(1));
  const res = await post({ ...PEDIDO, empresa: "Bot SA" });
  assert.equal(res.status, 200);
  assert.equal(calls.length, 0);
});

test("con TURNSTILE_SECRET exige token válido", async () => {
  const env = { ...ENV, TURNSTILE_SECRET: "ts" };
  const calls = fakeOdoo(c => c.url.includes("turnstile")
    ? new Response(JSON.stringify({ success: JSON.parse(JSON.stringify(Object.fromEntries(c.body))).response === "bueno" }))
    : rpc(JSON.parse(c.body).params.method === "authenticate" ? 7 : { ok: true, estado: "revision", cotizacion: "S1" }));
  assert.equal((await post(PEDIDO, { env })).status, 400);                       // sin token
  assert.equal((await post({ ...PEDIDO, turnstile: "malo" }, { env })).status, 400);
  assert.equal((await post({ ...PEDIDO, turnstile: "bueno" }, { env })).status, 200);
  assert.ok(calls.some(c => c.url.includes("erp.example")));
});

test("las demás rutas siguen sirviendo el sitio", async () => {
  const res = await worker.fetch(new Request("https://gatheringsgt.com/"), ENV);
  assert.equal(res.status, 200);
});
