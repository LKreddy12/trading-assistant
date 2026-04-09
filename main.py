from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.api import portfolio, signals, indicators, health, ask
from app.api.watchlist import router as watchlist_router
from app.api.analytics import router as analytics_router
from app.api.agent import router as agent_router

app = FastAPI(title="Trading Assistant API", version="2.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_db()

app.include_router(health.router,        prefix="/api")
app.include_router(portfolio.router,     prefix="/api/portfolio")
app.include_router(signals.router,       prefix="/api/signals")
app.include_router(indicators.router,    prefix="/api/indicators")
app.include_router(ask.router,           prefix="/api/ask")
app.include_router(watchlist_router,     prefix="/api/watchlist")
app.include_router(analytics_router,     prefix="/api/analytics")
app.include_router(agent_router,         prefix="/api/agent")
