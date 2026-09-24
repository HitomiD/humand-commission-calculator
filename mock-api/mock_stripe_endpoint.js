// ============================================================================
// Endpoint de pagos (entorno de evaluación) — Desafío AI Process Builder
// ============================================================================
// Este endpoint reemplaza, a los fines del ejercicio, la API de pagos de Stripe.
// Entrega datos de prueba y replica el comportamiento de una API productiva:
// pagina los resultados por cursor (igual que Stripe) y ocasionalmente responde
// 429 (rate limit) para que la integración contemple reintentos. No accede a
// datos reales ni a ninguna cuenta.
//
// No es necesario modificar este archivo. El objetivo es consumirlo desde la
// herramienta como un servicio externo: traer la totalidad de los pagos
// paginando y manejando correctamente las respuestas 429.
//
// Ubicación
// ----------------------------------------------------------------------------
// - Next.js (App Router): guardar como  app/api/stripe/payments/route.js
//   y utilizar la versión "App Router" (activa por defecto).
// - Proyecto Vercel sin framework / Next Pages API / despliegue independiente:
//   utilizar la versión "Node" incluida al final, como  api/stripe.js
//
// Una vez desplegada la aplicación en Vercel, el endpoint queda disponible en:
//   https://TU-APP.vercel.app/api/stripe/payments
// ============================================================================

//export const dynamic = 'force-dynamic';

const PAYMENTS = [
  {
    "deal_id": "D01",
    "payment_id": "D01_m1",
    "payment_date": "2025-01-01",
    "amount": 252.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D01",
    "payment_id": "D01_m2",
    "payment_date": "2025-02-01",
    "amount": 252.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D01",
    "payment_id": "D01_m3",
    "payment_date": "2025-03-01",
    "amount": 252.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D01",
    "payment_id": "D01_m4",
    "payment_date": "2025-04-01",
    "amount": 252.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D01",
    "payment_id": "D01_m5",
    "payment_date": "2025-05-01",
    "amount": 252.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D01",
    "payment_id": "D01_p06",
    "payment_date": "2026-06-01",
    "amount": 300.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D02",
    "payment_id": "D02_p_anual_y1",
    "payment_date": "2025-01-01",
    "amount": 25200.0,
    "payment_term": "anual",
    "currency": "USD"
  },
  {
    "deal_id": "D02",
    "payment_id": "D02_p13",
    "payment_date": "2027-01-01",
    "amount": 2500.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D03",
    "payment_id": "D03_p01",
    "payment_date": "2026-03-01",
    "amount": 5040.0,
    "payment_term": "anual",
    "currency": "USD"
  },
  {
    "deal_id": "D04",
    "payment_id": "D04_p01",
    "payment_date": "2026-02-01",
    "amount": 7200.0,
    "payment_term": "anual",
    "currency": "USD"
  },
  {
    "deal_id": "D05",
    "payment_id": "D05_m1",
    "payment_date": "2025-01-01",
    "amount": 700.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D05",
    "payment_id": "D05_m2",
    "payment_date": "2025-02-01",
    "amount": 700.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D05",
    "payment_id": "D05_m3",
    "payment_date": "2025-03-01",
    "amount": 700.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D05",
    "payment_id": "D05_m4",
    "payment_date": "2025-04-01",
    "amount": 700.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D05",
    "payment_id": "D05_p05",
    "payment_date": "2026-05-01",
    "amount": 8664.0,
    "payment_term": "anual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_m1",
    "payment_date": "2025-01-01",
    "amount": 561.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_m2",
    "payment_date": "2025-02-01",
    "amount": 561.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_m3",
    "payment_date": "2025-03-01",
    "amount": 561.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_m4",
    "payment_date": "2025-04-01",
    "amount": 561.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_m5",
    "payment_date": "2025-05-01",
    "amount": 561.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_m6",
    "payment_date": "2025-06-01",
    "amount": 561.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_m7",
    "payment_date": "2025-07-01",
    "amount": 561.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_m8",
    "payment_date": "2025-08-01",
    "amount": 561.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D06",
    "payment_id": "D06_p09",
    "payment_date": "2026-09-01",
    "amount": 3600.0,
    "payment_term": "semestral",
    "currency": "USD"
  },
  {
    "deal_id": "D07",
    "payment_id": "D07_p01",
    "payment_date": "2026-04-01",
    "amount": 12000.0,
    "payment_term": "anual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m1",
    "payment_date": "2025-01-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m2",
    "payment_date": "2025-02-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m3",
    "payment_date": "2025-03-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m4",
    "payment_date": "2025-04-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m5",
    "payment_date": "2025-05-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m6",
    "payment_date": "2025-06-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m7",
    "payment_date": "2025-07-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m8",
    "payment_date": "2025-08-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m9",
    "payment_date": "2025-09-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m10",
    "payment_date": "2025-10-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m11",
    "payment_date": "2025-11-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_m12",
    "payment_date": "2025-12-01",
    "amount": 1350.0,
    "payment_term": "mensual",
    "currency": "USD"
  },
  {
    "deal_id": "D08",
    "payment_id": "D08_p13",
    "payment_date": "2027-01-01",
    "amount": 1400.0,
    "payment_term": "mensual",
    "currency": "USD"
  }
];

// Proporción de respuestas 429 (rate limit). Ajustable segun se necesite.
const THROTTLE_RATE = 0.3;
const RETRY_AFTER_SECONDS = 2;

// ---- Version App Router (Next.js) ------------------------------------------
// export async function GET(request) {
//   // Simulacion de rate limit: una fraccion de las solicitudes responde 429.
//   if (Math.random() < THROTTLE_RATE) {
//     return new Response(
//       JSON.stringify({ error: { type: 'rate_limit_error', message: 'Too many requests. Retry after the seconds in Retry-After.' } }),
//       { status: 429, headers: { 'Retry-After': String(RETRY_AFTER_SECONDS), 'Content-Type': 'application/json' } }
//     );
//   }
//   const { searchParams } = new URL(request.url);
//   const limit = Math.min(parseInt(searchParams.get('limit')) || 5, 100);
//   const startingAfter = searchParams.get('starting_after');
//   let start = 0;
//   if (startingAfter) {
//     const i = PAYMENTS.findIndex(p => p.payment_id === startingAfter);
//     start = i >= 0 ? i + 1 : 0;
//   }
//   const data = PAYMENTS.slice(start, start + limit);
//   const has_more = start + limit < PAYMENTS.length;
//   return Response.json({ object: 'list', data, has_more });
// }

// ---- Version Node / Vercel function (despliegue independiente) -------------
// Utilizar esta version en lugar de la anterior si el proyecto no usa App Router.
 module.exports = (req, res) => {
   if (Math.random() < THROTTLE_RATE) {
     res.setHeader('Retry-After', String(RETRY_AFTER_SECONDS));
     return res.status(429).json({ error: { type: 'rate_limit_error', message: 'Too many requests.' } });
   }
   const limit = Math.min(parseInt(req.query.limit) || 5, 100);
   const startingAfter = req.query.starting_after;
   let start = 0;
   if (startingAfter) {
     const i = PAYMENTS.findIndex(p => p.payment_id === startingAfter);
     start = i >= 0 ? i + 1 : 0;
   }
   const data = PAYMENTS.slice(start, start + limit);
   const has_more = start + limit < PAYMENTS.length;
   return res.status(200).json({ object: 'list', data, has_more });
 };