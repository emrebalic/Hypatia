from fastapi import FastAPI

from app.analyze import router as analyze_router
from app.philosopher import router as philosopher_router
from app.transcribe import router as transcribe_router

app = FastAPI(title="Hypatia")
app.include_router(transcribe_router)
app.include_router(analyze_router)
app.include_router(philosopher_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
