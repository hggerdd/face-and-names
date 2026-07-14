"""
Central registry for person identities stored outside the database.

The registry is the source of truth for person IDs and display metadata.
SQLite databases mirror this data for convenience, but all mutations happen
against this registry first to keep IDs stable across multiple DB files.
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PersonRecord:
    """Structured person entry stored in the registry file."""

    id: int
    primary_name: str
    first_name: str = ""
    last_name: str = ""
    short_name: str | None = None
    birthdate: str | None = None
    notes: str | None = None
    aliases: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "primary_name": self.primary_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "short_name": self.short_name,
            "birthdate": self.birthdate,
            "notes": self.notes,
            "aliases": list(self.aliases),
        }


class RegistryFormatError(ValueError):
    """Raised when an existing registry cannot be safely loaded."""


class PersonRegistry:
    """JSON-backed registry that keeps person IDs stable across databases."""

    VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {"version": self.VERSION, "next_id": 1, "people": []}
        self._index: dict[int, PersonRecord] = {}
        self._load()

    # Public API ----------------------------------------------------------
    def list_people(self) -> list[PersonRecord]:
        return [self._copy_person(p) for p in self._index.values()]

    def has_person(self, person_id: int) -> bool:
        return person_id in self._index

    def get(self, person_id: int) -> PersonRecord:
        if person_id not in self._index:
            raise KeyError(f"Person {person_id} not found in registry")
        return self._copy_person(self._index[person_id])

    def add_person(
        self,
        *,
        first_name: str,
        last_name: str,
        short_name: str | None = None,
        birthdate: str | None = None,
        notes: str | None = None,
        aliases: list[dict[str, str]] | None = None,
        person_id: int | None = None,
    ) -> int:
        pid = self._reserve_id(preferred=person_id)
        primary = self._display_name(first_name, last_name, short_name)
        record = PersonRecord(
            id=pid,
            primary_name=primary,
            first_name=first_name or "",
            last_name=last_name or "",
            short_name=short_name,
            birthdate=birthdate,
            notes=notes,
            aliases=[],
        )
        for alias in aliases or []:
            self._add_alias_to_record(record, alias["name"], alias.get("kind", "alias"))
        self._index[pid] = record
        self._data["people"] = [p.to_dict() for p in self._index.values()]
        self._persist()
        return pid

    def rename_person(
        self, person_id: int, *, first_name: str, last_name: str, short_name: str | None = None
    ) -> None:
        record = self._require(person_id)
        record.first_name = first_name or ""
        record.last_name = last_name or ""
        record.short_name = short_name
        record.primary_name = self._display_name(first_name, last_name, short_name)
        self._index[person_id] = record
        self._data["people"] = [p.to_dict() for p in self._index.values()]
        self._persist()

    def add_alias(self, person_id: int, name: str, kind: str = "alias") -> None:
        record = self._require(person_id)
        self._add_alias_to_record(record, name, kind)
        self._data["people"] = [p.to_dict() for p in self._index.values()]
        self._persist()

    def merge_people(self, source_ids: list[int], target_id: int) -> None:
        to_merge = [pid for pid in source_ids if pid != target_id]
        if not to_merge:
            return
        target = self._require(target_id)
        for pid in to_merge:
            record = self._require(pid)
            for alias in record.aliases:
                self._add_alias_to_record(target, alias["name"], alias.get("kind", "alias"))
            if record.primary_name and not any(
                a.get("kind") == "primary" and a.get("name") == record.primary_name
                for a in target.aliases
            ):
                self._add_alias_to_record(target, record.primary_name, "merged")
            self._index.pop(pid, None)
        self._data["people"] = [p.to_dict() for p in self._index.values()]
        self._persist()

    def replace_people(self, people: list[dict[str, Any]]) -> None:
        """Replace the registry with provided records (used for bootstrap)."""
        self._index.clear()
        self._data = {"version": self.VERSION, "next_id": 1, "people": []}
        for person in people:
            pid = int(person["id"])
            self._data["next_id"] = max(self._data["next_id"], pid + 1)
            record = PersonRecord(
                id=pid,
                primary_name=str(person.get("primary_name") or ""),
                first_name=str(person.get("first_name") or ""),
                last_name=str(person.get("last_name") or ""),
                short_name=person.get("short_name"),
                birthdate=person.get("birthdate"),
                notes=person.get("notes"),
                aliases=[],
            )
            for alias in person.get("aliases") or []:
                self._add_alias_to_record(record, alias.get("name", ""), alias.get("kind", "alias"))
            self._index[pid] = record
        self._data["people"] = [p.to_dict() for p in self._index.values()]
        self._persist()

    def snapshot(self) -> bytes | None:
        """Return the current on-disk registry for coordinated transactions."""
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def restore(self, snapshot: bytes | None) -> None:
        """Restore a previously captured registry snapshot atomically."""
        if snapshot is None:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(snapshot)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
            except Exception:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
        self._load()

    # Internal helpers ----------------------------------------------------
    def _reserve_id(self, preferred: int | None = None) -> int:
        if preferred is not None and preferred not in self._index:
            if preferred >= self._data["next_id"]:
                self._data["next_id"] = preferred + 1
            return preferred
        pid = int(self._data["next_id"])
        self._data["next_id"] = pid + 1
        return pid

    def _add_alias_to_record(self, record: PersonRecord, name: str, kind: str) -> None:
        name = name.strip()
        if not name:
            return
        if any(a["name"] == name and a.get("kind") == kind for a in record.aliases):
            return
        record.aliases.append({"name": name, "kind": kind})

    def _display_name(self, first: str | None, last: str | None, short: str | None) -> str:
        if short:
            return short
        combined = " ".join(filter(None, [first, last])).strip()
        return combined or ""

    def _require(self, person_id: int) -> PersonRecord:
        if person_id not in self._index:
            raise KeyError(f"Person {person_id} not found in registry")
        return self._index[person_id]

    def _copy_person(self, record: PersonRecord) -> PersonRecord:
        return PersonRecord(**deepcopy(record.to_dict()))

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RegistryFormatError(f"Unable to read person registry {self.path}") from exc
            if not isinstance(data, dict):
                raise RegistryFormatError("Person registry root must be a JSON object")
            if data.get("version") != self.VERSION:
                raise RegistryFormatError(
                    f"Unsupported person registry version: {data.get('version')!r}"
                )
            if not isinstance(data.get("people"), list):
                raise RegistryFormatError("Person registry 'people' must be a list")
            self._data = data
        else:
            self._persist()
        self._index = {}
        for person in self._data.get("people", []):
            if not isinstance(person, dict) or "id" not in person:
                raise RegistryFormatError("Each registry person must be an object with an id")
            try:
                record = PersonRecord(
                    id=int(person["id"]),
                    primary_name=str(person.get("primary_name") or ""),
                    first_name=str(person.get("first_name") or ""),
                    last_name=str(person.get("last_name") or ""),
                    short_name=person.get("short_name"),
                    birthdate=person.get("birthdate"),
                    notes=person.get("notes"),
                    aliases=list(person.get("aliases") or []),
                )
            except (TypeError, ValueError) as exc:
                raise RegistryFormatError("Invalid person record in registry") from exc
            if record.id in self._index:
                raise RegistryFormatError(f"Duplicate person id in registry: {record.id}")
            self._index[record.id] = record
            self._data["next_id"] = max(int(self._data.get("next_id", 1)), record.id + 1)
        self._data.setdefault("next_id", 1)

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self._data)
        payload.update(
            {
                "version": self.VERSION,
                "next_id": int(self._data.get("next_id", 1)),
                "people": [p.to_dict() for p in self._index.values()],
            }
        )
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise


def default_registry_path(base_dir: Path | None = None) -> Path:
    """Return the default path for the person registry file."""
    root = base_dir or Path.cwd()
    return root / "persons" / "persons.json"
