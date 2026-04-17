"""FastAPI entry point for JobPilot."""

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.events import router as events_router
from api.routes import router as core_router

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jobpilot")

app = FastAPI(title="JobPilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(core_router)
app.include_router(events_router)
