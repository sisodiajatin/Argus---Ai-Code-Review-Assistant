"""Smoke test for the rotated GitHub App key. Do not merge."""

import os


def read_user_file(name: str) -> str:
    # path traversal: name may contain "../"
    with open(os.path.join("/srv/uploads", name)) as f:
        return f.read()
