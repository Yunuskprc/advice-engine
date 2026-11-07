from fastapi import Request

from app.clients.ollama import LlmClient
from app.config import AppSettings
from app.db import Database
from app.jobs import JobRunner


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_runner(request: Request) -> JobRunner:
    return request.app.state.runner


def get_llm(request: Request) -> LlmClient:
    return request.app.state.llm


def get_app_settings(request: Request) -> AppSettings:
    return request.app.state.settings
