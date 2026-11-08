from fastapi import Request

from app.clients.ollama import LlmClient
from app.config import AppSettings, RecommenderSettings
from app.db import Database
from app.jobs import JobRunner
from app.services.vector_index import VectorIndex


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_runner(request: Request) -> JobRunner:
    return request.app.state.runner


def get_vector_index(request: Request) -> VectorIndex:
    return request.app.state.vector_index


def get_llm(request: Request) -> LlmClient:
    return request.app.state.llm


def get_app_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_rec_settings(request: Request) -> RecommenderSettings:
    return request.app.state.rec
