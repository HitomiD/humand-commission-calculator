"use strict";

const http = require('node:http');
const handler = require('./mock_stripe_endpoint.js');

const port = Number(process.env.MOCK_PORT || 4000);

http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (req.method !== 'GET' || url.pathname !== '/api/stripe/payments') {
    res.writeHead(404).end('Not found');
    return;
  }

  req.query = Object.fromEntries(url.searchParams);
  res.status = function (code) {
    this.statusCode = code;
    return this;
  };
  res.json = function (body) {
    this.setHeader('Content-Type', 'application/json');
    this.end(JSON.stringify(body));
  };

  handler(req, res);
}).listen(port, '0.0.0.0', () => {
  console.log(`Payment mock listening on http://localhost:${port}/api/stripe/payments`);
});

