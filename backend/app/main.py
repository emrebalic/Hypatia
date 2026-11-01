from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.analyze import router as analyze_router
from app.content_api import router as content_router
from app.demo import router as demo_router
from app.philosopher import router as philosopher_router
from app.transcribe import router as transcribe_router

app = FastAPI(title="Hypatia")
# The Vite dev server (and a separately served production build) calls the
# API cross-origin; without CORS the browser blocks every /api response.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(transcribe_router)
app.include_router(analyze_router)
app.include_router(philosopher_router)
app.include_router(demo_router)
app.include_router(content_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
