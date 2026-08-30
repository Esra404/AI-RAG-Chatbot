import os

import uvicorn


if __name__ == "__main__":
    reload_enabled = os.getenv("DEV_RELOAD", "false").lower() == "true"
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=reload_enabled)
