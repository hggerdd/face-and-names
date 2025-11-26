from __future__ import annotations

import json

import pytest

from face_and_names.services.person_registry import PersonRegistry


@pytest.fixture
def registry_file(tmp_path):
    return tmp_path / "persons.json"

@pytest.fixture
def registry(registry_file):
    return PersonRegistry(registry_file)

def test_init_creates_empty_registry(registry_file):
    reg = PersonRegistry(registry_file)
    assert reg.list_people() == []
    assert registry_file.exists()
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    assert data["people"] == []
    assert data["next_id"] == 1

def test_add_person(registry):
    pid = registry.add_person(first_name="John", last_name="Doe")
    assert pid == 1
    person = registry.get(pid)
    assert person.first_name == "John"
    assert person.last_name == "Doe"
    assert person.primary_name == "John Doe"
    assert registry.has_person(pid)

def test_add_person_with_aliases(registry):
    pid = registry.add_person(
        first_name="Jane", 
        last_name="Doe", 
        aliases=[{"name": "Janey", "kind": "nickname"}]
    )
    person = registry.get(pid)
    assert len(person.aliases) == 1
    assert person.aliases[0]["name"] == "Janey"
    assert person.aliases[0]["kind"] == "nickname"

def test_rename_person(registry):
    pid = registry.add_person(first_name="John", last_name="Doe")
    registry.rename_person(pid, first_name="Johnny", last_name="Doe")
    person = registry.get(pid)
    assert person.first_name == "Johnny"
    assert person.primary_name == "Johnny Doe"

def test_add_alias(registry):
    pid = registry.add_person(first_name="John", last_name="Doe")
    registry.add_alias(pid, "Johnny")
    person = registry.get(pid)
    assert any(a["name"] == "Johnny" for a in person.aliases)

def test_merge_people(registry):
    p1 = registry.add_person(first_name="Keep", last_name="Me")
    p2 = registry.add_person(first_name="Merge", last_name="Me")
    registry.add_alias(p2, "Mergy")
    
    registry.merge_people([p2], p1)
    
    assert registry.has_person(p1)
    assert not registry.has_person(p2)
    
    person1 = registry.get(p1)
    # Check that p2's alias was moved
    assert any(a["name"] == "Mergy" for a in person1.aliases)
    # Check that p2's name was added as merged alias
    assert any(a["name"] == "Merge Me" and a["kind"] == "merged" for a in person1.aliases)

def test_replace_people(registry):
    registry.add_person(first_name="Old", last_name="Data")
    new_data = [
        {
            "id": 10,
            "primary_name": "New Person",
            "first_name": "New",
            "last_name": "Person",
            "aliases": [{"name": "NP", "kind": "alias"}]
        }
    ]
    registry.replace_people(new_data)
    
    assert not registry.has_person(1)
    assert registry.has_person(10)
    person = registry.get(10)
    assert person.primary_name == "New Person"
    assert person.aliases[0]["name"] == "NP"

def test_persistence(registry_file):
    reg1 = PersonRegistry(registry_file)
    reg1.add_person(first_name="Persist", last_name="Me")
    
    reg2 = PersonRegistry(registry_file)
    assert len(reg2.list_people()) == 1
    assert reg2.list_people()[0].first_name == "Persist"
