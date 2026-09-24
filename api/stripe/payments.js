// Vercel entry point for the payment mock.
//
// Vercel's file-based routing maps this file to /api/stripe/payments and runs
// it as a Node function. Filesystem routes take precedence over the rewrites in
// vercel.json, so this path reaches the mock instead of FastAPI.
//
// The handler itself (payment data, cursor pagination and simulated 429s) lives
// in mock-api/mock_stripe_endpoint.js, which the local dev server also loads.
// Re-exporting it here keeps a single copy of the mock logic.
module.exports = require('../../mock-api/mock_stripe_endpoint.js');
