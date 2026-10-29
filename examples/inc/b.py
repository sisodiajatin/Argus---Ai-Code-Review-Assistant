"""Incremental review test, file B. Do not merge."""

import json


def load_session(blob: bytes) -> dict:
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("session must be a JSON object")
    return data
