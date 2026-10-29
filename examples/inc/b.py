"""Incremental review test, file B. Do not merge."""

import pickle


def load_session(blob: bytes):
    return pickle.loads(blob)
