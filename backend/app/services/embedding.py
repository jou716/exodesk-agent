from __future__ import annotations

import hashlib
import math
import re

from .glossary import expand_query


DIMENSION = 384
WORD_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_\-.]*|[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    expanded = expand_query(text).lower()
    tokens = WORD_RE.findall(expanded)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", expanded)
    for run in chinese_runs:
        for index in range(len(run) - 1):
            tokens.append(run[index : index + 2])
    return tokens


def tokenize(text: str) -> list[str]:
    return _tokens(text)


def embed_text(text: str) -> list[float]:
    vector = [0.0] * DIMENSION
    tokens = _tokens(text)
    for position, token in enumerate(tokens):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % DIMENSION
        sign = 1.0 if digest[4] & 1 else -1.0
        weight = 1.0 if position < len(tokens) * 0.7 else 0.6
        vector[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 8) for value in vector]


def embed_texts(texts: list[str]) -> list[list[float]]:
    return [embed_text(text) for text in texts]

