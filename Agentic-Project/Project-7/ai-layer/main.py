from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from api.builder import router as builder_router
import os

load_dotenv()

app = FastAPI(
    title=os.getenv("APP_NAME", "AI Layer"),
    version=os.getenv("APP_VERSION", "1.0.0"),
    description="Agentic AI Platform - AI Layer"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(builder_router, prefix="/api")


@app.get("/")
def root():
    return {
        "service": "AI Layer",
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "status": "running"
    }


@app.get("/health")
def health():
    return {
        "service": "AI Layer",
        "status": "healthy"
    }