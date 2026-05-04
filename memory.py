import os
from datetime import datetime


def _memory_path(cwd: str) -> str:
    return os.path.join(cwd, ".cipher", "memory.md")


def load_memory(cwd: str) -> str:
    path = _memory_path(cwd)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return f.read()
        except Exception:
            return ""
    return ""


def save_memory(cwd: str, content: str):
    path = _memory_path(cwd)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def append_memory(cwd: str, entry: str):
    path = _memory_path(cwd)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(path, "a") as f:
        f.write(f"\n### {timestamp}\n{entry}\n")
