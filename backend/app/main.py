import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import config
from app.routes import auth, me, projects, tasks, ws
from app.ws.manager import hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.loop = asyncio.get_running_loop()
    yield


app = FastAPI(title="TaskFlow API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(projects.router)
api.include_router(tasks.router)
api.include_router(me.router)
app.include_router(api)
app.include_router(ws.router, prefix="/api")  # ws://host/api/ws


@app.get("/api/health")
def health():
    return {"status": "ok"}
