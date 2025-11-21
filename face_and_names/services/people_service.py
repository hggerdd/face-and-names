"""
People and groups management service.
"""

from __future__ import annotations

import sqlite3

from face_and_names.models.repositories import (
    GroupRepository,
    PersonAliasRepository,
    PersonGroupRepository,
    PersonRepository,
)


class PeopleService:
    """People and groups management service with merge hooks."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._ensure_person_schema()
        self.people = PersonRepository(conn)
        self.aliases = PersonAliasRepository(conn)
        self.groups = GroupRepository(conn)
        self.person_groups = PersonGroupRepository(conn)

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

    def create_person(
        self,
        first_name: str,
        last_name: str,
        short_name: str | None = None,
        aliases: list[str] | None = None,
        birthdate: str | None = None,
        notes: str | None = None,
    ) -> int:
        person_id = self.people.create(
            first_name=first_name,
            last_name=last_name,
            short_name=short_name,
            birthdate=birthdate,
            notes=notes,
        )
        for alias in aliases or []:
            try:
                self.aliases.add_alias(person_id, alias, kind="alias")
            except sqlite3.IntegrityError:
                # Ignore duplicate aliases during creation
                continue
        self.conn.commit()
        return person_id

    def merge_people(self, source_ids: list[int], target_id: int) -> None:
        to_merge = [pid for pid in source_ids if pid != target_id]
        if not to_merge:
            return
        placeholders = ", ".join("?" for _ in to_merge)

        params = [target_id, *to_merge]
        # Rebind faces and predictions
        self.conn.execute(f"UPDATE face SET person_id = ? WHERE person_id IN ({placeholders})", params)
        self.conn.execute(
            f"UPDATE face SET predicted_person_id = ? WHERE predicted_person_id IN ({placeholders})", params
        )
        # Rebind group memberships
        self.conn.execute(
            f"UPDATE person_group SET person_id = ? WHERE person_id IN ({placeholders})",
            params,
        )
        # Move aliases
        for pid in to_merge:
            for name, kind in self._aliases_for(pid):
                try:
                    self.aliases.add_alias(target_id, name, kind=kind)
                except sqlite3.IntegrityError:
                    continue
        # Delete merged people
        self.conn.execute(f"DELETE FROM person WHERE id IN ({placeholders})", to_merge)
        self.conn.commit()

    def _aliases_for(self, person_id: int) -> list[tuple[str, str]]:
        rows = self.conn.execute(
            "SELECT name, kind FROM person_alias WHERE person_id = ?", (person_id,)
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def add_alias(self, person_id: int, name: str, kind: str = "alias") -> int:
        alias_id = self.aliases.add_alias(person_id, name, kind=kind)
        self.conn.commit()
        return alias_id

    def list_people(self) -> list[dict]:
        counts = {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT person_id, COUNT(*) FROM face WHERE person_id IS NOT NULL GROUP BY person_id"
            ).fetchall()
        }
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(person)")}
        if "first_name" in cols:
            rows = self.conn.execute(
                "SELECT id, primary_name, first_name, last_name, short_name, birthdate, notes FROM person ORDER BY primary_name"
            ).fetchall()
            is_legacy = False
        else:
            rows = self.conn.execute(
                "SELECT id, primary_name, birthdate, notes FROM person ORDER BY primary_name"
            ).fetchall()
            is_legacy = True
        people: list[dict] = []
        for row in rows:
            pid = int(row[0])
            if is_legacy:
                display = self.display_name(None, None, None, row[1])
                people.append(
                    {
                        "id": pid,
                        "primary_name": row[1],
                        "first_name": "",
                        "last_name": "",
                        "short_name": None,
                        "display_name": display,
                        "birthdate": row[2],
                        "notes": row[3],
                        "face_count": counts.get(pid, 0),
                        "aliases": [{"name": name, "kind": kind} for name, kind in self._aliases_for(pid)],
                    }
                )
            else:
                display = self.display_name(row[2], row[3], row[4], row[1])
                people.append(
                    {
                        "id": pid,
                        "primary_name": row[1],
                        "first_name": row[2],
                        "last_name": row[3],
                        "short_name": row[4],
                        "display_name": display,
                        "birthdate": row[5],
                        "notes": row[6],
                        "face_count": counts.get(pid, 0),
                        "aliases": [{"name": name, "kind": kind} for name, kind in self._aliases_for(pid)],
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
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(person)")}
        display = self.display_name(first_name, last_name, short_name)
        if {"first_name", "last_name", "short_name"}.issubset(cols):
            self.conn.execute(
                "UPDATE person SET primary_name = ?, first_name = ?, last_name = ?, short_name = ? WHERE id = ?",
                (display, first_name, last_name, short_name, person_id),
            )
        else:
            self.conn.execute("UPDATE person SET primary_name = ? WHERE id = ?", (display, person_id))
        self.conn.commit()
