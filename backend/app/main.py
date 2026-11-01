from fastapi import FastAPI

from app.transcribe import router as transcribe_router

app = FastAPI(title="Hypatia")
app.include_router(transcribe_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
