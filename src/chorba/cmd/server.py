from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from chorba.lib.markup._schema_org import ensure_ingredient_parser_ready
from chorba.web.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_ingredient_parser_ready()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Chorba API", lifespan=lifespan)

    app.include_router(router)

    return app


app = create_app()


def main():
    uvicorn.run("chorba.cmd.server:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
