#!/usr/bin/env python3
"""Render OpenViking's runtime config from non-secret defaults and env secrets."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("OPENVIKING_CONFIG_FILE", "/app/.openviking/ov.conf"))
ROOT_API_KEY = os.environ.get("OPENVIKING_ROOT_API_KEY", "").strip()
VLM_MODEL = os.environ.get("OPENVIKING_VLM_MODEL", "gpt-5.6-luna").strip()

PLACEHOLDER_API_KEY = "replace-with-64-random-hex-characters"
if ROOT_API_KEY == PLACEHOLDER_API_KEY or re.fullmatch(r"[0-9a-fA-F]{64}", ROOT_API_KEY) is None:
    raise SystemExit("OPENVIKING_ROOT_API_KEY must contain exactly 64 hexadecimal characters")
if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", VLM_MODEL) is None:
    raise SystemExit("OPENVIKING_VLM_MODEL must contain a valid model identifier")

config = {
    "server": {
        "host": "0.0.0.0",
        "port": 1933,
        "root_api_key": ROOT_API_KEY,
        "cors_origins": [],
    },
    "storage": {
        "workspace": "/app/.openviking/data",
        "vectordb": {
            "name": "context",
            "backend": "local",
            "project": "default",
        },
        "agfs": {
            "backend": "local",
            "timeout": 10,
        },
    },
    "embedding": {
        "dense": {
            "provider": "ollama",
            "model": "nomic-embed-text",
            "api_base": "http://openviking-ollama:11434/v1",
            "dimension": 768,
            "input": "text",
        },
        "text_source": "content_only",
        "max_input_tokens": 4096,
    },
    "vlm": {
        "provider": "openai-codex",
        "model": VLM_MODEL,
        "api_base": "https://chatgpt.com/backend-api/codex",
        "temperature": 0.0,
        "max_retries": 2,
    },
    "retrieval": {
        "hotness_alpha": 0.0,
        "score_propagation_alpha": 1.0,
    },
    "auto_generate_l0": True,
    "auto_generate_l1": True,
    "default_search_mode": "thinking",
    "default_search_limit": 6,
    "memory": {
        "version": "v3",
        "extraction_enabled": True,
        "session_skill_extraction_enabled": False,
    },
    "encryption": {
        "enabled": True,
        "provider": "local",
        "local": {"key_file": "/app/.openviking/master.key"},
        "api_key_hashing": {"enabled": True},
    },
    "log": {
        "level": "INFO",
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "output": "stdout",
        "rotation": False,
    },
}

CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
fd, temporary_name = tempfile.mkstemp(prefix="ov.conf.", dir=CONFIG_PATH.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary_name, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(temporary_name, CONFIG_PATH)
    directory_fd = os.open(CONFIG_PATH.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
finally:
    try:
        os.unlink(temporary_name)
    except FileNotFoundError:
        pass
