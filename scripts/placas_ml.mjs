// Busca placas para el agente de casa en Mercado Libre Argentina.
//
// ML bloquea a curl y a los navegadores headless con un captcha o un pedido
// de login, así que esto abre tu Chrome con un perfil propio (scripts/.ml-profile,
// ignorado por git). La primera vez iniciás sesión en esa ventana; las
// siguientes corre solo mientras ML mantenga la cookie.
//
//   cd scripts && npm install && node placas_ml.mjs [--paginas 1] [--salida out/placas.json]
//
// Deja un JSON con {query, titulo, precio, url, vendedor, vendidos, full, usado}
// que después puntúa rank_placas.py con Jev.

import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const QUERIES = [
  "raspberry pi 4",
  "raspberry pi 5",
  "raspberry pi 3 b+",
  "raspberry pi zero 2 w",
  "orange pi zero 3",
  "orange pi 3b",
  "orange pi 5",
  "radxa zero 3",
  "radxa rock",
  "banana pi",
  "libre computer le potato",
  "odroid",
  "mini pc n100",
  "mini pc n95",
  "thin client",
  "dell wyse",
  "hp t630",
];

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : def;
};
const paginas = Number(opt("--paginas", "1"));
const salida = resolve(opt("--salida", "out/placas.json"));
const debug = args.includes("--debug");
const soloPrimera = args.includes("--solo-primera");

// Ordenado por precio ascendente: lo barato primero, que es lo que buscamos.
const urlDe = (q, pagina) => {
  const slug = q.trim().replace(/\s+/g, "-");
  const desde = pagina > 1 ? `_Desde_${(pagina - 1) * 48 + 1}` : "";
  return `https://listado.mercadolibre.com.ar/${slug}${desde}_OrderId_PRICE_ASC_NoIndex_True`;
};

const esVerificacion = (url) =>
  url.includes("account-verification") || url.includes("/login") || url.includes("captcha");

async function esperarLogin(page) {
  if (!esVerificacion(page.url())) return;
  console.error("ML pide un captcha o login. Resolvelo en la ventana de Chrome; sigo solo cuando cargue el listado.");
  for (let i = 0; i < 300; i++) {
    await page.waitForTimeout(2000);
    if (!esVerificacion(page.url()) && (await page.$(".poly-card, .ui-search-result"))) return;
  }
  throw new Error("Pasaron 10 minutos sin login.");
}

async function extraer(page, query) {
  return page.$$eval(
    ".poly-card, .ui-search-result",
    (cards, query) =>
      cards.map((c) => {
        const t = c.textContent?.replace(/\s+/g, " ") ?? "";
        const titulo =
          c.querySelector(".poly-component__title, h3, h2")?.textContent?.trim() ?? "";
        const precioTxt =
          c.querySelector(".poly-price__current .andes-money-amount__fraction")?.textContent ??
          c.querySelector(".andes-money-amount__fraction")?.textContent ??
          "";
        const precio = Number(precioTxt.replace(/\./g, "")) || null;
        const link = c.querySelector(".poly-component__title[href], a[href*='mercadolibre.com.ar']");
        const url = link?.getAttribute("href")?.split("#")[0] ?? "";
        const vendedor = c.querySelector(".poly-component__seller")?.textContent?.replace(/^Por\s+/i, "").trim() ?? "";
        const vendidos = Number((t.match(/\+?(\d[\d.]*)\s*vendidos?/i)?.[1] ?? "0").replace(/\./g, ""));
        return {
          query,
          titulo,
          precio,
          url,
          vendedor,
          vendidos,
          full: /\bFULL\b/i.test(t) || !!c.querySelector("[aria-label*='Full'], .poly-component__shipped-from"),
          usado: /\bUsado\b/i.test(t) || /\bReacondicionado\b/i.test(t),
        };
      }),
    query,
  );
}

const ctx = await chromium.launchPersistentContext(resolve(".ml-profile"), {
  channel: "chrome",
  headless: false,
  locale: "es-AR",
  viewport: { width: 1280, height: 900 },
});
const page = ctx.pages()[0] ?? (await ctx.newPage());
const items = new Map();

try {
  for (const q of soloPrimera ? QUERIES.slice(0, 1) : QUERIES) {
    for (let p = 1; p <= paginas; p++) {
      await page.goto(urlDe(q, p), { waitUntil: "domcontentloaded", timeout: 60000 });
      await esperarLogin(page);
      await page.waitForSelector(".poly-card, .ui-search-result", { timeout: 20000 }).catch(() => null);
      const encontrados = await extraer(page, q);
      if (debug && encontrados.length === 0) {
        console.error("URL:", page.url(), "TITLE:", await page.title());
        console.error(await page.$eval("body", (b) => b.innerText.slice(0, 1500)));
        console.error(await page.$eval("body", (b) => b.innerHTML.slice(0, 2500)));
      }
      let nuevos = 0;
      for (const it of encontrados) {
        if (!it.url || !it.precio) continue;
        if (!items.has(it.url)) nuevos++;
        items.set(it.url, it);
      }
      console.error(`${q} p${p}: ${encontrados.length} avisos, ${nuevos} nuevos`);
      if (encontrados.length < 40) break;
      // Un respiro entre páginas: no hace falta apurar a ML.
      await page.waitForTimeout(1500 + Math.random() * 1500);
    }
  }
} finally {
  await ctx.close();
}

await mkdir(dirname(salida), { recursive: true });
await writeFile(salida, JSON.stringify([...items.values()], null, 1));
console.error(`${items.size} avisos únicos en ${salida}`);
