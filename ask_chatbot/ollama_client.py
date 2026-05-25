import shutil
import subprocess
import sys

from ask_chatbot import DEFAULT_MODEL


def creation_flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def ollama_available():
    return shutil.which("ollama") is not None


def list_installed_models(timeout=8):
    if not ollama_available():
        return [], "Ollama was not found in PATH."

    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags(),
        timeout=timeout,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or "Ollama returned an error while listing models."
        return [], message

    models = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            models.append(parts[0])

    if DEFAULT_MODEL not in models:
        models.insert(0, DEFAULT_MODEL)

    return models, None


def build_run_command(model_name):
    return ["ollama", "run", model_name]
