# Commission calculator

This repository holds a commission payment calculator engine for the Humand partner program. It serves as the technical challenge for the  "AI Process Builder" selection process.

The calculator and payment mock live in separate source directories. Vercel serves them as Python and Node functions in one project.

## Run the calculator locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn api.index:app --reload --port 8000
```

Open `http://localhost:8000/`. The initial calculator response is `{"message":"hello world from calculator"}`.

## Run the payment mock locally

In another terminal:

```bash
node mock-api/dev-server.cjs
```

The mock endpoint is `http://localhost:4000/api/stripe/payments`. It may return HTTP 429; retry after the `Retry-After` interval. The local server and Vercel function import the same handler from `mock-api/handler.cjs`.
