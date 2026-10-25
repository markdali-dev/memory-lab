import tempfile
import unittest
from pathlib import Path

from memlab.memory import MemoryStore, MemoryStoreError


class MemoryStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.tmp.name) / "m.json", today=lambda: "2026-10-25")

    def tearDown(self):
        self.tmp.cleanup()

    def propose(self, statement="Revenue is the sum of Invoice.Total.", type="definition",
                topic="revenue", **kw):
        return self.store.propose(type, topic, statement, source="test", proposed_by="analyst", **kw)

    def test_propose_then_accept(self):
        r = self.propose()
        self.assertEqual(r, {"result": "proposed", "id": "M001", "possible_duplicates": []})
        self.assertEqual(self.store.lookup("revenue"), [])          # proposals are invisible
        self.store.accept("M001", "manager")
        m = self.store.lookup("Revenue")[0]                          # topic is normalized
        self.assertEqual((m["status"], m["reviewed_by"], m["last_verified"]), ("accepted", "manager", "2026-10-25"))

    def test_exact_duplicate_is_refused(self):
        self.propose()
        r = self.propose("  revenue is the SUM of invoice.total ")
        self.assertEqual((r["result"], r["id"]), ("duplicate", "M001"))
        self.assertEqual(len(self.store._load()), 1)

    def test_near_duplicate_is_flagged(self):
        self.propose()
        r = self.propose("Revenue is the sum of the Invoice.Total column.")
        self.assertEqual(r["result"], "proposed")
        self.assertEqual(r["possible_duplicates"], ["M001"])

    def test_supersede_replaces_old_decision(self):
        self.propose("Use BillingCountry for country questions.", type="decision", topic="geography")
        self.store.accept("M001", "manager")
        self.propose("Use Customer.Country for country questions.", type="decision", topic="geography",
                     supersedes="M001")
        self.store.accept("M002", "manager")
        old, new = self.store.get("M001"), self.store.get("M002")
        self.assertEqual((old["status"], old["superseded_by"]), ("superseded", "M002"))
        self.assertEqual([m["id"] for m in self.store.lookup("geography")], ["M002"])
        self.assertIn("[M002]", self.store.index())
        self.assertNotIn("[M001]", self.store.index())

    def test_cannot_supersede_twice(self):
        self.propose("A.", type="decision"); self.store.accept("M001", "manager")
        self.propose("B.", type="decision", supersedes="M001")
        self.propose("C.", type="decision", supersedes="M001")
        self.store.accept("M002", "manager")
        with self.assertRaises(MemoryStoreError):
            self.store.accept("M003", "manager")                     # M001 already replaced

    def test_reject_needs_reason(self):
        self.propose()
        with self.assertRaises(MemoryStoreError):
            self.store.reject("M001", "manager", "")
        self.store.reject("M001", "manager", "Wrong: Total includes tax")
        self.assertEqual(self.store.get("M001")["status"], "rejected")
        self.assertEqual(self.propose()["result"], "proposed")         # rejected ones don't block

    def test_validation(self):
        with self.assertRaises(MemoryStoreError):
            self.propose(type="opinion")
        with self.assertRaises(MemoryStoreError):
            self.propose("x" * 300)
        with self.assertRaises(MemoryStoreError):
            self.propose(topic="!!!")
        with self.assertRaises(MemoryStoreError):
            self.propose(confidence="certain")

    def test_index_shows_decisions_and_topics_only(self):
        self.propose("Always report money in USD.", type="decision", topic="money"); self.store.accept("M001", "m")
        self.propose("Invoice dates run 2009 to 2013.", type="fact", topic="dates"); self.store.accept("M002", "m")
        self.propose("Pending idea.", type="fact", topic="dates")
        idx = self.store.index()
        self.assertIn("[M001] (money) Always report money in USD.", idx)
        self.assertNotIn("2009", idx)                                  # facts are tier 2
        self.assertIn("- dates: 1 fact", idx)
        self.assertIn("1 proposal(s) waiting", idx)

    def test_index_budget_warning(self):
        for i in range(40):
            self.propose(f"Decision number {i} about a long and specific rule for the analyst agent.",
                         type="decision", topic=f"t{i}")
            self.store.accept(f"M{i + 1:03d}", "m")
        self.assertIn("WARNING", self.store.index(budget_tokens=800))

    def test_search(self):
        self.propose(); self.store.accept("M001", "m")
        self.assertEqual(len(self.store.search("invoice total")), 1)
        self.assertEqual(self.store.search("customer"), [])


if __name__ == "__main__":
    unittest.main()
