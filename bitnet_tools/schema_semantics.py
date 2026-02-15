from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

SCHEMA_SEMANTICS_PATH = Path(__file__).resolve().parents[1] / "resources" / "schema_semantics_ko.json"


@dataclass
class AliasConcept:
    canonical: str
    aliases: list[str]
    column_aliases: list[str]


@dataclass
class AliasMatch:
    user_term: str
    status: str
    canonical: str | None = None
    matched_column: str | None = None
    candidates: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_term": self.user_term,
            "status": self.status,
            "canonical": self.canonical,
            "matched_column": self.matched_column,
            "candidates": self.candidates or [],
        }


def _norm(text: str) -> str:
    return "".join(ch for ch in str(text).strip().lower() if not ch.isspace() and ch not in "_-")


def load_schema_semantics(path: str | Path | None = None) -> list[AliasConcept]:
    semantics_path = Path(path) if path else SCHEMA_SEMANTICS_PATH
    raw = json.loads(semantics_path.read_text(encoding="utf-8"))
    items = raw.get("concepts", []) if isinstance(raw, dict) else []

    concepts: list[AliasConcept] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        canonical = str(item.get("canonical", "")).strip()
        if not canonical:
            continue
        aliases = [str(x).strip() for x in item.get("aliases", []) if str(x).strip()]
        col_aliases = [str(x).strip() for x in item.get("column_aliases", []) if str(x).strip()]
        concepts.append(AliasConcept(canonical=canonical, aliases=aliases, column_aliases=col_aliases))
    return concepts


def match_alias_to_column(user_term: str, columns: list[str], concepts: list[AliasConcept]) -> AliasMatch:
    term_key = _norm(user_term)
    if not term_key:
        return AliasMatch(user_term=user_term, status="failed")

    concept: AliasConcept | None = None
    for c in concepts:
        vocab = {_norm(c.canonical), *(_norm(a) for a in c.aliases)}
        if term_key in vocab:
            concept = c
            break

    if concept is None:
        return AliasMatch(user_term=user_term, status="failed")

    candidate_keys = {_norm(concept.canonical), *(_norm(a) for a in concept.column_aliases), *(_norm(a) for a in concept.aliases)}
    candidates = [col for col in columns if _norm(col) in candidate_keys]

    if len(candidates) == 1:
        return AliasMatch(
            user_term=user_term,
            status="success",
            canonical=concept.canonical,
            matched_column=candidates[0],
            candidates=candidates,
        )
    if len(candidates) > 1:
        return AliasMatch(
            user_term=user_term,
            status="ambiguous",
            canonical=concept.canonical,
            candidates=candidates,
        )
    return AliasMatch(user_term=user_term, status="failed", canonical=concept.canonical)


def normalize_question_entities(question: str, columns: list[str], concepts: list[AliasConcept]) -> dict[str, Any]:
    normalized_question = question
    mappings: list[AliasMatch] = []

    for concept in concepts:
        terms = [concept.canonical, *concept.aliases]
        for term in terms:
            if term and term in question:
                match = match_alias_to_column(term, columns, concepts)
                mappings.append(match)
                if match.status == "success" and match.matched_column:
                    normalized_question = normalized_question.replace(term, match.matched_column)
                break

    deduped: dict[str, AliasMatch] = {}
    for item in mappings:
        deduped[item.user_term] = item

    return {
        "normalized_question": normalized_question,
        "mappings": [m.to_dict() for m in deduped.values()],
    }
