"""Calculator web application."""

from fastapi import FastAPI

app = FastAPI(title="Commission calculator")


@app.get("/")
@app.get("/api")
def hello() -> dict[str, str]:
    return {"message": "hello world from calculator"}

