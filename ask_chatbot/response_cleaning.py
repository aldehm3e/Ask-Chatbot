import re


ANSI_ESCAPE_RE = re.compile(r"[\x1b\x9b\u2039]\[[0-?]*[ -/]*[@-~]")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
OPEN_THINK_RE = re.compile(r"<think>.*$", re.IGNORECASE | re.DOTALL)


def _strip_terminal_noise(text):
    text = ANSI_ESCAPE_RE.sub("", text)
    return CONTROL_CHAR_RE.sub("", text)


def clean_model_response(text):
    """Remove model reasoning tags, terminal control characters, and stream artifacts."""
    text = _strip_terminal_noise(text)
    text = THINK_BLOCK_RE.sub("", text)
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)

    lines = []
    for line in text.splitlines():
        line = line.rstrip()
        if lines and line:
            previous_word = re.search(r"(\w{1,16})$", lines[-1], flags=re.UNICODE)
            first_word = re.match(r"(\w{1,32})", line, flags=re.UNICODE)
            if (
                previous_word
                and first_word
                and first_word.group(1).casefold().startswith(previous_word.group(1).casefold())
                and first_word.group(1).casefold() != previous_word.group(1).casefold()
            ):
                lines[-1] = lines[-1][: -len(previous_word.group(1))].rstrip()
        lines.append(line)

    return "\n".join(lines).strip()


def clean_partial_model_response(text):
    """Clean streamed text while hiding any unfinished reasoning block."""
    text = _strip_terminal_noise(text)
    text = THINK_BLOCK_RE.sub("", text)
    text = OPEN_THINK_RE.sub("", text)
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    return text.strip()
