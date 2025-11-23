"""
People and groups management service backed by a central registry file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from face_and_names.models.repositories import (
    GroupRepository,
    PersonAliasRepository,
    PersonGroupRepository,
    PersonRepository,
)
from face_and_names.services.person_registry import PersonRegistry, default_registry_path


class PeopleService:
    """People and groups management service with merge hooks and registry sync."""

    def __init__(self, conn: sqlite3.Connection, registry_path: Path | None = None) -> None:
        self.conn = conn
        self.registry_path = registry_path or default_registry_path()
        self._ensure_person_schema()
        self.registry = PersonRegistry(self.registry_path)
        self.people = PersonRepository(conn)
        self.aliases = PersonAliasRepository(conn)
        self.groups = GroupRepository(conn)
        self.person_groups = PersonGroupRepository(conn)
        self._synchronize_registry_and_db()

    def _ensure_person_schema(self) -> None:
        """Add missing person columns for legacy databases."""
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(person)")}
        if "first_name" not in cols:
            self.conn.execute("ALTER TABLE person ADD COLUMN first_name TEXT NOT NULL DEFAULT ''")
        if "last_name" not in cols:
            self.conn.execute("ALTER TABLE person ADD COLUMN last_name TEXT NOT NULL DEFAULT ''")
        if "short_name" not in cols:
            self.conn.execute("ALTER TABLE person ADD COLUMN short_name TEXT")
        if {"first_name", "last_name", "short_name", "primary_name"}.issubset(cols) is False:
            self.conn.commit()

    @staticmethod
    def display_name(
        first_name: str | None = None,
        last_name: str | None = None,
        short_name: str | None = None,
        primary_name: str | None = None,
    ) -> str:
        if short_name:
            return short_name
        combined = " ".join(filter(None, [first_name, last_name])).strip()
        return combined or (primary_name or "")

    # Registry-aware API --------------------------------------------------
    def create_person(
        self,
        first_name: str,
        last_name: str,
        short_name: str | None = None,
        aliases: list[str] | None = None,
        birthdate: str | None = None,
        notes: str | None = None,
    ) -> int:
        pid = self.registry.add_person(
            first_name=first_name,
            last_name=last_name,
            short_name=short_name,
            birthdate=birthdate,
            notes=notes,
            aliases=[{"name": alias, "kind": "alias"} for alias in aliases or []],
        )
        self._rewrite_person_tables()
        return pid

    def merge_people(self, source_ids: list[int], target_id: int) -> None:
        to_merge = [pid for pid in source_ids if pid != target_id]
        if not to_merge:
            return
        self.registry.merge_people(source_ids, target_id)
        mapping = {pid: target_id for pid in to_merge}
        self._remap_person_ids(mapping)
        self._rewrite_person_tables()
        self.conn.commit()

    def add_alias(self, person_id: int, name: str, kind: str = "alias") -> int:
        self.registry.add_alias(person_id, name, kind=kind)
        try:
            alias_id = self.aliases.add_alias(person_id, name, kind=kind)
        except sqlite3.IntegrityError:
            alias_id = int(
                self.conn.execute(
                    "SELECT id FROM person_alias WHERE person_id = ? AND name = ? AND kind = ?",
                    (person_id, name, kind),
                ).fetchone()[0]
            )
        self.conn.commit()
        return alias_id

    def list_people(self) -> list[dict]:
        counts = {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT person_id, COUNT(*) FROM face WHERE person_id IS NOT NULL GROUP BY person_id"
            ).fetchall()
        }
        people: list[dict[str, Any]] = []
        for record in sorted(self.registry.list_people(), key=lambda r: r.primary_name.lower() if r.primary_name else ""):
            pid = record.id
            display = self.display_name(record.first_name, record.last_name, record.short_name, record.primary_name)
            people.append(
                {
                    "id": pid,
                    "primary_name": record.primary_name,
                    "first_name": record.first_name,
                    "last_name": record.last_name,
                    "short_name": record.short_name,
                    "display_name": display,
                    "birthdate": record.birthdate,
                    "notes": record.notes,
                    "face_count": counts.get(pid, 0),
                    "aliases": list(record.aliases),
                }
            )
        return people

    def create_group(
        self,
        name: str,
        parent_group_id: int | None = None,
        description: str | None = None,
        color: str | None = None,
    ) -> int:
        gid = self.groups.create(name=name, parent_group_id=parent_group_id, description=description, color=color)
        self.conn.commit()
        return gid

    def assign_groups(self, person_id: int, group_ids: list[int]) -> None:
        self.person_groups.add_memberships(person_id, group_ids)
        self.conn.commit()

    def rename_person(
        self, person_id: int, first_name: str, last_name: str, short_name: str | None = None
    ) -> None:
        self.registry.rename_person(person_id, first_name=first_name, last_name=last_name, short_name=short_name)
        self._rewrite_person_tables()
        self.conn.commit()

    # Synchronization helpers --------------------------------------------
    def _synchronize_registry_and_db(self) -> None:
        """Ensure registry is authoritative while absorbing legacy DB rows."""
        db_people = self._load_people_from_db()
        registry_people = self.registry.list_people()

        if not registry_people and db_people:
            # Bootstrap registry from DB if registry is empty
            self.registry.replace_people(db_people)
            registry_people = self.registry.list_people()

        # Absorb DB-only IDs, remapping if the ID slot is already used
        remap: dict[int, int] = {}
        for person in db_people:
            pid = int(person["id"])
            if self.registry.has_person(pid):
                continue
            new_id = self.registry.add_person(
                first_name=person.get("first_name", ""),
                last_name=person.get("last_name", ""),
                short_name=person.get("short_name"),
                birthdate=person.get("birthdate"),
                notes=person.get("notes"),
                aliases=person.get("aliases") or [],
                person_id=pid,
            )
            remap[pid] = new_id

        if remap:
            self._remap_person_ids(remap)

        # Finally, rewrite DB tables from registry snapshot
        self._rewrite_person_tables()

    def _load_people_from_db(self) -> list[dict[str, Any]]:
        """Load people + aliases from DB for migration/bootstrap."""
        alias_rows = self.conn.execute("SELECT person_id, name, kind FROM person_alias").fetchall()
        aliases: dict[int, list[dict[str, str]]] = {}
        for pid, name, kind in alias_rows:
            aliases.setdefault(int(pid), []).append({"name": name, "kind": kind})

        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(person)")}
        if "first_name" in cols:
            rows = self.conn.execute(
                "SELECT id, primary_name, first_name, last_name, short_name, birthdate, notes FROM person ORDER BY id"
            ).fetchall()
            people = [
                {
                    "id": int(row[0]),
                    "primary_name": row[1],
                    "first_name": row[2],
                    "last_name": row[3],
                    "short_name": row[4],
                    "birthdate": row[5],
                    "notes": row[6],
                    "aliases": aliases.get(int(row[0]), []),
                }
                for row in rows
            ]
        else:
            rows = self.conn.execute(
                "SELECT id, primary_name, birthdate, notes FROM person ORDER BY id"
            ).fetchall()
            people = [
                {
                    "id": int(row[0]),
                    "primary_name": row[1],
                    "first_name": "",
                    "last_name": "",
                    "short_name": None,
                    "birthdate": row[2],
                    "notes": row[3],
                    "aliases": aliases.get(int(row[0]), []),
                }
                for row in rows
            ]
        return people

    def _rewrite_person_tables(self) -> None:
        """Mirror registry state into SQLite person + alias tables."""
        self.conn.execute("DELETE FROM person_alias")
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(person)")}
        has_full_name_cols = {"first_name", "last_name", "short_name"}.issubset(cols)
        max_id = 0
        registry_people = self.registry.list_people()
        registry_ids = {p.id for p in registry_people}
        for person in registry_people:
            max_id = max(max_id, person.id)
            if has_full_name_cols:
                self.conn.execute(
                    """
                    INSERT INTO person (id, primary_name, first_name, last_name, short_name, birthdate, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        primary_name=excluded.primary_name,
                        first_name=excluded.first_name,
                        last_name=excluded.last_name,
                        short_name=excluded.short_name,
                        birthdate=excluded.birthdate,
                        notes=excluded.notes
                    """,
                    (
                        person.id,
                        person.primary_name,
                        person.first_name,
                        person.last_name,
                        person.short_name,
                        person.birthdate,
                        person.notes,
                    ),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO person (id, primary_name, birthdate, notes)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        primary_name=excluded.primary_name,
                        birthdate=excluded.birthdate,
                        notes=excluded.notes
                    """,
                    (person.id, person.primary_name, person.birthdate, person.notes),
                )
            for alias in person.aliases:
                try:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO person_alias (person_id, name, kind) VALUES (?, ?, ?)",
                        (person.id, alias.get("name"), alias.get("kind", "alias")),
                    )
                except sqlite3.IntegrityError:
                    continue
        if registry_ids:
            placeholders = ", ".join("?" for _ in registry_ids)
            self.conn.execute(f"DELETE FROM person WHERE id NOT IN ({placeholders})", list(registry_ids))
        else:
            # Only clear the table if there are no dependent rows
            linked = self.conn.execute(
                "SELECT COUNT(*) FROM face WHERE person_id IS NOT NULL OR predicted_person_id IS NOT NULL"
            ).fetchone()[0]
            linked_groups = self.conn.execute("SELECT COUNT(*) FROM person_group").fetchone()[0]
            if linked == 0 and linked_groups == 0:
                self.conn.execute("DELETE FROM person")
        if max_id > 0:
            try:
                self.conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'person'", (max_id,))
            except sqlite3.OperationalError:
                # sqlite_sequence may not exist depending on table creation flags
                pass
        self.conn.commit()

    def _remap_person_ids(self, mapping: dict[int, int]) -> None:
        """Update foreign keys when we must reassign person IDs."""
        for old_id, new_id in mapping.items():
            if old_id == new_id:
                continue
            self.conn.execute("UPDATE face SET person_id = ? WHERE person_id = ?", (new_id, old_id))
            self.conn.execute(
                "UPDATE face SET predicted_person_id = ? WHERE predicted_person_id = ?", (new_id, old_id)
            )
            self.conn.execute("UPDATE person_alias SET person_id = ? WHERE person_id = ?", (new_id, old_id))
            self.conn.execute("UPDATE person_group SET person_id = ? WHERE person_id = ?", (new_id, old_id))
