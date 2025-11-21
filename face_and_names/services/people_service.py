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
        self.people = PersonRepository(conn)
        self.aliases = PersonAliasRepository(conn)
        self.groups = GroupRepository(conn)
        self.person_groups = PersonGroupRepository(conn)

    def create_person(
        self,
        name: str,
        aliases: list[str] | None = None,
        birthdate: str | None = None,
        notes: str | None = None,
    ) -> int:
        person_id = self.people.create(primary_name=name, birthdate=birthdate, notes=notes)
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
        rows = self.conn.execute(
            "SELECT id, primary_name, birthdate, notes FROM person ORDER BY primary_name"
        ).fetchall()
        people: list[dict] = []
        for row in rows:
            pid = int(row[0])
            people.append(
                {
                    "id": pid,
                    "primary_name": row[1],
                    "birthdate": row[2],
                    "notes": row[3],
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

    def rename_person(self, person_id: int, new_name: str) -> None:
        self.conn.execute("UPDATE person SET primary_name = ? WHERE id = ?", (new_name, person_id))
        self.conn.commit()
