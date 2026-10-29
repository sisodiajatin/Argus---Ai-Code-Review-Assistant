"""Deliberately vulnerable code used to smoke-test Argus. Do not merge."""

import sqlite3
import subprocess

DB_PASSWORD = "hunter2"  # hardcoded credential


def run(cmd: str) -> int:
    # command injection: user input goes straight to a shell
    return subprocess.call(cmd, shell=True)


def find_user(conn: sqlite3.Connection, name: str):
    # SQL injection: string formatting instead of parameters
    return conn.execute(f"SELECT * FROM users WHERE name = '{name}'").fetchall()


def average(values: list[float]) -> float:
    # crashes on an empty list
    return sum(values) / len(values)

# retrigger 02:28:57
# retrigger 02:24:18
# retrigger 02:27:41
