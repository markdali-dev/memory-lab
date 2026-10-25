import sqlite3
import unittest

from memlab import db


class DbTest(unittest.TestCase):
    def test_query(self):
        r = db.query("SELECT COUNT(*) AS n FROM Invoice")
        self.assertEqual(r["columns"], ["n"])
        self.assertEqual(r["rows"], [[412]])
        self.assertFalse(r["truncated"])

    def test_row_cap(self):
        r = db.query("SELECT TrackId FROM Track")
        self.assertEqual(r["row_count"], db.MAX_ROWS)
        self.assertTrue(r["truncated"])

    def test_read_only(self):
        with self.assertRaises(sqlite3.OperationalError):
            db.query("DELETE FROM Invoice")
        self.assertEqual(db.query("SELECT COUNT(*) FROM Invoice")["rows"], [[412]])

    def test_schema(self):
        s = db.schema()
        self.assertIn("Invoice (412 rows): InvoiceId, CustomerId", s)
        self.assertEqual(len(s.splitlines()), 11)


if __name__ == "__main__":
    unittest.main()
