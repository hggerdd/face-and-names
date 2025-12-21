import sqlite3
import unittest
from datetime import date
from unittest.mock import MagicMock

from face_and_names.services.advanced_search_service import (
    AdvancedSearchService,
    FilterType,
    LogicOperator,
    SearchCriterion,
    fuzzy_match,
)
from face_and_names.services.people_service import PeopleService


class TestAdvancedSearch(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE person (id INTEGER PRIMARY KEY, primary_name TEXT)")
        self.conn.execute(
            "CREATE TABLE image (id INTEGER PRIMARY KEY, relative_path TEXT, thumbnail_blob BLOB, import_id INTEGER)"
        )
        self.conn.execute(
            "CREATE TABLE face (id INTEGER PRIMARY KEY, image_id INTEGER, person_id INTEGER)"
        )
        self.conn.execute("CREATE TABLE import_session (id INTEGER PRIMARY KEY, import_date TEXT)")
        self.conn.execute("CREATE TABLE metadata (image_id INTEGER, key TEXT, value TEXT)")

        # Mock PeopleService
        self.people_service = MagicMock(spec=PeopleService)
        self.people_service.conn = self.conn

        self.service = AdvancedSearchService(self.people_service)

        # Seed data
        self.conn.execute("INSERT INTO person (id, primary_name) VALUES (1, 'John Doe')")
        self.conn.execute("INSERT INTO person (id, primary_name) VALUES (2, 'Jane Smith')")
        self.conn.execute("INSERT INTO image (id, relative_path) VALUES (1, 'img1.jpg')")
        self.conn.execute("INSERT INTO image (id, relative_path) VALUES (2, 'img2.jpg')")
        self.conn.execute("INSERT INTO face (image_id, person_id) VALUES (1, 1)")  # John in img1
        self.conn.execute("INSERT INTO face (image_id, person_id) VALUES (2, 2)")  # Jane in img2
        self.conn.execute("INSERT INTO import_session (id, import_date) VALUES (1, '2023-01-01')")
        self.conn.execute("UPDATE image SET import_id = 1")

    def tearDown(self):
        self.conn.close()

    def test_fuzzy_match_function(self):
        self.assertEqual(fuzzy_match("John Doe", "john"), 1.0)  # Substring
        self.assertGreater(fuzzy_match("John Doe", "jon"), 0.6)  # Fuzzy
        self.assertEqual(fuzzy_match("John Doe", "xyz"), 0.0)  # No match

    def test_search_exact_name(self):
        criteria = [
            SearchCriterion(
                filter_type=FilterType.NAME_FUZZY,
                operator=LogicOperator.AND,
                value={"name": "John", "threshold": 1.0},
            )
        ]
        results = self.service.search(criteria)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].image_id, 1)

    def test_search_fuzzy_name(self):
        criteria = [
            SearchCriterion(
                filter_type=FilterType.NAME_FUZZY,
                operator=LogicOperator.AND,
                value={"name": "jon", "threshold": 0.4},
            )
        ]
        results = self.service.search(criteria)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].image_id, 1)

    def test_search_or_logic(self):
        # Name is John OR Name is Jane
        criteria = [
            SearchCriterion(
                filter_type=FilterType.NAME_FUZZY,
                operator=LogicOperator.AND,
                value={"name": "John", "threshold": 1.0},
            ),
            SearchCriterion(
                filter_type=FilterType.NAME_FUZZY,
                operator=LogicOperator.OR,
                value={"name": "Jane", "threshold": 1.0},
            ),
        ]
        results = self.service.search(criteria)
        self.assertEqual(len(results), 2)

    def test_search_date_range(self):
        # Date 2023-01-01 is in range
        criteria = [
            SearchCriterion(
                filter_type=FilterType.DATE_RANGE,
                operator=LogicOperator.AND,
                value={"start": date(2022, 12, 31), "end": date(2023, 1, 2)},
            )
        ]
        results = self.service.search(criteria)
        self.assertEqual(len(results), 2)  # Both images imported on 2023-01-01

    def test_person_count(self):
        # Img1 has 1 face. Img2 has 1 face.
        # Add another face to Img1
        self.conn.execute("INSERT INTO face (image_id, person_id) VALUES (1, 2)")

        criteria = [
            SearchCriterion(
                filter_type=FilterType.PERSON_COUNT,
                operator=LogicOperator.AND,
                value={"operator": ">", "count": 1},
            )
        ]
        results = self.service.search(criteria)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].image_id, 1)


if __name__ == "__main__":
    unittest.main()
