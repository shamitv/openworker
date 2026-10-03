"""Frozen v1 matching, shared by asset validation and execution scoring."""

from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("_", " ")
    text = re.sub(r"g\s*/\s*m(?:2|²)", "gsm", text)
    text = re.sub(r"\b(\d+)\s*gsm\b", r"\1 gsm", text)
    text = re.sub(r"(?<=\d)\s*(khz|hz)\b", r" \1", text)
    return " ".join(re.sub(r"(?<!\d)\.|\.(?!\d)|[^\w\s.]", " ", text).split())


def matches_value(value: str, fact: dict) -> bool:
    normalized = " " + normalize(value) + " "
    return all(any(" " + normalize(alias) + " " in normalized for alias in group) for group in fact["value_alias_groups"])


def matches_record(record: dict, fact: dict, persona: dict) -> bool:
    actor = "peer" if fact["subject"] == "peer" else "owner"
    workspace = persona["workspaces"][fact["workspace"]] if fact["workspace"] else None
    return (
        record["user_id"] == persona["namespaces"][actor]
        and record["workspace_id"] == workspace and record["scope"] == fact["scope"]
        and normalize(record["key"]) in {normalize(alias) for alias in fact["key_aliases"]}
        and matches_value(record["value"], fact)
    )
