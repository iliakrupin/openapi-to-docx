"""
FastAPI application entry point.
"""
from fastapi import FastAPI

from src.routers import documentation

app = FastAPI(
    title="OpenAPI to Docx Generator",
    description="A FastAPI-based service that converts OpenAPI 3.0+ JSON specifications into comprehensive Markdown documentation and exports it as DOCX files.",
    version="1.0.0",
)

app.include_router(documentation.router)
