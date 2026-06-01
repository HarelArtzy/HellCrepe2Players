import logging
import os
import re
from typing import Any, cast

from env_config import OLLAMA_MODEL

try:
    from ollama import chat as ollama_chat
    from ollama import list as ollama_list
except Exception:  # pragma: no cover - keeps game runnable without ollama
    ollama_chat = None
    ollama_list = None


logger = logging.getLogger(__name__)


DEFAULT_OLLAMA_MODEL = OLLAMA_MODEL
FALLBACK_NAME = "Crepe Knight"


def _clean_name(raw_name: str) -> str:
    text = raw_name.strip()
    if not text:
        return ""

    first_line = text.splitlines()[0].strip()
    first_line = first_line.strip("\"'` ")

    lowered = first_line.lower()
    if lowered.startswith("name:"):
        first_line = first_line.split(":", 1)[1].strip()

    first_line = re.sub(r"[^A-Za-z0-9 '\-]", "", first_line)
    first_line = re.sub(r"\s+", " ", first_line).strip()
    return first_line[:20]


def _extract_model_name(entry: Any) -> str:
    name = getattr(entry, "model", None)
    if not name and isinstance(entry, dict):
        name = entry.get("model")
    return str(name).strip() if name else ""


def _list_local_models() -> list[str]:
    if ollama_list is None:
        return []
    list_fn = cast(Any, ollama_list)
    try:
        response = list_fn()
    except Exception:
        logger.exception("Failed to list local Ollama models")
        return []

    names: list[str] = []
    for entry in getattr(response, "models", []) or []:
        name = _extract_model_name(entry)
        if name and name not in names:
            names.append(name)
    return names


def _build_model_candidates(requested_model: str | None) -> list[str]:
    env_model = os.getenv("OLLAMA_MODEL", "").strip()
    local_models = _list_local_models()

    candidates: list[str] = []
    for name in (requested_model or "", env_model, DEFAULT_OLLAMA_MODEL, *local_models):
        cleaned = str(name).strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    return candidates


def generate_dungeon_fighter_crepe_name(model: str | None = None) -> str:
    """Generate a short crepe fighter name from a local Ollama model."""
    if ollama_chat is None:
        logger.warning("The 'ollama' package is not installed; using fallback name")
        return FALLBACK_NAME
    chat_fn = cast(Any, ollama_chat)

    candidates = _build_model_candidates(model)
    if not candidates:
        logger.warning("No Ollama model candidates found; using fallback name")
        return FALLBACK_NAME

    for candidate in candidates:
        try:
            response = chat_fn(
                model=candidate,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You create short fantasy names for action game characters."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Return one original name for a dungeon fighter crepe. "
                            "Output only the name. Max 20 characters. The name should include the word Crepe or "
                            "something related to it."
                        ),
                    },
                ],
                stream=False,
                options={"temperature": 1.1},
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                logger.warning("Ollama model not found: '%s'", candidate)
                continue
            if "not found" in str(exc).lower():
                logger.warning("Ollama model not found: '%s'", candidate)
                continue
            logger.exception("Ollama request failed for model '%s'", candidate)
            continue

        content = ""
        try:
            content = response.message.content or ""
        except AttributeError:
            content = str(response.get("message", {}).get("content", ""))

        cleaned_name = _clean_name(content)
        if cleaned_name:
            return cleaned_name

    logger.warning("All Ollama model attempts failed; using fallback name")
    return FALLBACK_NAME
