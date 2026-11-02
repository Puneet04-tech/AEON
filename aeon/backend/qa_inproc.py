"""Minimal repro isolation: BaseHTTPMiddleware + endpoint that declares a
FastAPI/Pydantic body model vs endpoint reading json manually.

The AEON /judge endpoint ALSO takes no Pydantic model (body parsed via
Request), while /login declares `body: LoginRequest`. Probe both variants
under plain Starlette+FastAPI to pinpoint the interaction.
"""
import asyncio
import time

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.testclient import TestClient


class LoginRequest(BaseModel):
    password: str


async def manual(request: Request):
    data = await request.json()
    return {"ok": True, "data": data}


async def modelled(body: LoginRequest):
    return {"ok": True, "data": body.password}


async def mw(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        raw = await request.body()
        request._body = raw
    return await call_next(request)


app = FastAPI()
app.add_middleware(BaseHTTPMiddleware, dispatch=mw)
app.post("/manual")(manual)
app.post("/modelled")(modelled)


def main():
    with TestClient(app, raise_server_exceptions=False) as client:
        for path in ("/manual", "/modelled"):
            t0 = time.time()
            try:
                r = client.post(path, json={"password": "x"}, timeout=6)
                print(path, r.status_code, round(time.time() - t0, 1))
            except Exception as e:
                print(path, "EXC:", type(e).__name__, round(time.time() - t0, 1))


if __name__ == "__main__":
    main()
