import os

import uvicorn


if __name__ == "__main__":
    reload_enabled = os.getenv("DEV_RELOAD", "false").lower() == "true"
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=reload_enabled)
