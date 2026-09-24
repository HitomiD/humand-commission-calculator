"use strict";

// Local development server for the payment mock.
//
// On Vercel, mock_stripe_endpoint.js runs as a Node function and Vercel
// supplies the request/response helpers it relies on. Locally there is no such
// runtime, so this file starts a plain Node HTTP server and adds the few Vercel
// helpers the handler uses (req.query, res.status(), res.json()) before
// calling the same handler. The mock logic stays in one file.
//
// Usage: node mock-api/dev-server.cjs   (port can be changed with MOCK_PORT)

const http = require('node:http');
const handler = require('./mock_stripe_endpoint.js');

const port = Number(process.env.MOCK_PORT || 4000);

http.createServer((req, res) => {
  // req.url is only a path; a base is needed to parse it with URL.
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

  // Serve only the route that exists on Vercel, so local URLs match production.
  if (req.method !== 'GET' || url.pathname !== '/api/stripe/payments') {
    res.writeHead(404).end('Not found');
    return;
  }

  // Vercel-style helpers expected by the handler:
  // - req.query: query-string parameters (limit, starting_after) as an object.
  req.query = Object.fromEntries(url.searchParams);
  // - res.status(code): sets the status code and returns res for chaining.
  res.status = function (code) {
    this.statusCode = code;
    return this;
  };
  // - res.json(body): serializes the body and ends the response.
  res.json = function (body) {
    this.setHeader('Content-Type', 'application/json');
    this.end(JSON.stringify(body));
  };

  handler(req, res);
}).listen(port, '0.0.0.0', () => {
  console.log(`Payment mock listening on http://localhost:${port}/api/stripe/payments`);
});
