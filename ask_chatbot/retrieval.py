import math
import re
from collections import Counter
from dataclasses import dataclass


TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "عن",
    "في",
    "ما",
    "من",
    "هو",
    "هي",
    "على",
    "إلى",
    "الى",
}


@dataclass
class RetrievedChunk:
    label: str
    chunk: object
    score: float


def tokenize(text):
    tokens = [match.group(0).casefold() for match in TOKEN_RE.finditer(text)]
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


def score_chunk(query_tokens, query_text, chunk):
    chunk_tokens = tokenize(chunk.text)
    if not chunk_tokens:
        return 0.0

    token_counts = Counter(chunk_tokens)
    unique_count = len(set(chunk_tokens))
    score = 0.0

    for token in query_tokens:
        if token in token_counts:
            score += 1.0 + math.log1p(token_counts[token])

    if query_text and query_text in chunk.text.casefold():
        score += 4.0

    file_name = chunk.file_name.casefold()
    for token in query_tokens:
        if token in file_name:
            score += 0.5

    if unique_count:
        score *= 1.0 + min(unique_count, 300) / 1000.0

    return score


def retrieve_relevant_chunks(query, chunks, limit=6, min_score=0.2):
    if not chunks:
        return []

    query_text = query.casefold().strip()
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    scored = []
    for chunk in chunks:
        score = score_chunk(query_tokens, query_text, chunk)
        if score >= min_score:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = scored[:limit]

    return [
        RetrievedChunk(label=f"S{index + 1}", chunk=chunk, score=score)
        for index, (score, chunk) in enumerate(selected)
    ]


def representative_chunks(chunks, limit=6):
    if not chunks:
        return []

    if len(chunks) <= limit:
        selected = chunks
    else:
        step = max(1, len(chunks) // limit)
        selected = [chunks[index] for index in range(0, len(chunks), step)][:limit]

    return [
        RetrievedChunk(label=f"S{index + 1}", chunk=chunk, score=0.0)
        for index, chunk in enumerate(selected)
    ]


def format_sources_for_prompt(retrieved_chunks):
    parts = []
    for item in retrieved_chunks:
        chunk = item.chunk
        parts.append(
            f"[{item.label}] {chunk.file_name}, page {chunk.page_number}, chunk {chunk.chunk_index}\n"
            f"{chunk.text}"
        )
    return "\n\n".join(parts)


def format_sources_for_display(retrieved_chunks):
    return [
        f"[{item.label}] {item.chunk.file_name}, page {item.chunk.page_number}, chunk {item.chunk.chunk_index}"
        for item in retrieved_chunks
    ]
