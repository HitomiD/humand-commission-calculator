"""Vercel entry point for the calculator engine.

Vercel's Python runtime discovers this file under the root ``api/`` directory
and serves the ASGI ``app`` it exposes. The rewrites in ``vercel.json`` send
``/`` and every ``/api/*`` path (except the mock's own file route,
``/api/stripe/payments``) here. The application itself lives in
``calculator/app.py``; this module only re-exports it so the calculator code
stays independent of Vercel's directory layout.
"""

from calculator.app import app  # noqa: F401  (re-exported for Vercel)
