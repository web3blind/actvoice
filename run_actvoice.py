from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("ACTVOICE_PORT", "3003"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, proxy_headers=True)
