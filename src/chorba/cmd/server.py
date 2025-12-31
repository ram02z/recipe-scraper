import uvicorn
from fastapi import FastAPI
from chorba.web.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Chorba API")

    app.include_router(router)

    return app


app = create_app()


def main():
    uvicorn.run("chorba.cmd.server:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
