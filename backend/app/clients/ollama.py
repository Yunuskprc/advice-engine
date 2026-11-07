"""Ollama istemcisi. Uygulama `LlmClient` arayüzüne bağımlıdır; testlerde fake kullanılır."""

from typing import Protocol

import httpx


class LlmClient(Protocol):
    def list_models(self, timeout: float | None = None) -> list[str]: ...

    def embed(self, model: str, inputs: list[str]) -> list[list[float]]: ...

    def generate(self, model: str, prompt: str, max_tokens: int | None = None) -> str: ...


def has_model(available: list[str], wanted: str) -> bool:
    """`bge-m3` ile `bge-m3:latest` eşleşir; etiket verilmişse tam eşleşme aranır."""
    if ":" in wanted:
        return wanted in available
    return any(name.split(":", 1)[0] == wanted for name in available)


class OllamaClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=timeout or self.timeout)

    def list_models(self, timeout: float | None = None) -> list[str]:
        with self._client(timeout) as c:
            r = c.get("/api/tags")
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]

    def embed(self, model: str, inputs: list[str]) -> list[list[float]]:
        with self._client() as c:
            r = c.post("/api/embed", json={"model": model, "input": inputs})
            r.raise_for_status()
            return r.json()["embeddings"]

    def generate(self, model: str, prompt: str, max_tokens: int | None = None) -> str:
        body: dict = {"model": model, "prompt": prompt, "stream": False, "think": False}
        if max_tokens is not None:
            body["options"] = {"num_predict": max_tokens}
        with self._client() as c:
            r = c.post("/api/generate", json=body)
            if r.status_code == 400 and "think" in r.text.lower():
                # Düşünme modu desteklemeyen modeller `think` alanını reddedebilir.
                body.pop("think")
                r = c.post("/api/generate", json=body)
            r.raise_for_status()
            return r.json()["response"]
