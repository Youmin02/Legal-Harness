"""Minimal immutable provision corpus abstraction."""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ProvisionDocument:
    provision_id: str
    statute_name: str
    provision_text: str


def legal_text_alias_key(document: ProvisionDocument) -> tuple[str, str]:
    """Return the exact legal-text identity used for snapshot alias collapse.

    The statute hierarchy is part of ``statute_name`` in the normalized corpus,
    so identical body text from different statutes remains distinct.
    """
    return (
        re.sub(r"\s+", " ", unicodedata.normalize("NFC", document.statute_name)).strip(),
        re.sub(r"\s+", " ", unicodedata.normalize("NFC", document.provision_text)).strip(),
    )


class InMemoryProvisionCorpus:
    def __init__(self, documents: Iterable[ProvisionDocument]):
        self._documents: Dict[str, ProvisionDocument] = {}
        for document in documents:
            if not document.provision_id or not document.provision_text:
                raise ValueError("provision_id and provision_text are required")
            if document.provision_id in self._documents:
                raise ValueError("duplicate provision_id: %s" % document.provision_id)
            self._documents[document.provision_id] = document

    def get(self, provision_id: str) -> Optional[ProvisionDocument]:
        return self._documents.get(provision_id)

    def all(self) -> List[ProvisionDocument]:
        return list(self._documents.values())

    @classmethod
    def from_jsonl(cls, path: Path) -> "InMemoryProvisionCorpus":
        documents: List[ProvisionDocument] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    documents.append(
                        ProvisionDocument(
                            provision_id=record["provision_id"],
                            statute_name=record["statute_name"],
                            provision_text=record["provision_text"],
                        )
                    )
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise ValueError("invalid corpus JSONL at line %d" % line_number) from exc
        return cls(documents)
