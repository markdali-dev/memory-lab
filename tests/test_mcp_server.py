"""End-to-end: start the real server as a subprocess and talk MCP to it,
exactly as Claude Code would."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class McpServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = dict(os.environ, MEMLAB_STORE=str(Path(self.tmp.name) / "m.json"))
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "memlab" / "mcp_server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env, cwd=self.tmp.name)
        self.next_id = 0

    def tearDown(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=5)
        self.proc.stdout.close()
        self.tmp.cleanup()

    def send(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            self.next_id += 1
            msg["id"] = self.next_id
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        if notify:
            return None
        reply = json.loads(self.proc.stdout.readline())
        self.assertEqual(reply["id"], self.next_id)
        return reply

    def call(self, name, **args):
        result = self.send("tools/call", {"name": name, "arguments": args})["result"]
        return result["isError"], result["content"][0]["text"]

    def test_handshake_and_tools(self):
        r = self.send("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "test", "version": "1"}})
        self.assertEqual(r["result"]["serverInfo"]["name"], "memlab")
        self.send("notifications/initialized", notify=True)     # no reply expected
        names = [t["name"] for t in self.send("tools/list")["result"]["tools"]]
        self.assertEqual(names, ["memory_index", "memory_lookup", "memory_search", "memory_propose",
                                 "memory_pending", "memory_review", "memory_verify", "db_schema", "db_query"])

    def test_feedback_loop_through_tools(self):
        self.send("initialize", {"protocolVersion": "2025-06-18"})
        err, text = self.call("memory_propose", type="decision", topic="dates",
                              statement="Treat 2013 as the current year; the data ends 2013-12-22.",
                              source="query result", proposed_by="analyst", confidence="high",
                              evidence="SELECT MAX(InvoiceDate) FROM Invoice")
        self.assertFalse(err)
        self.assertEqual(json.loads(text)["id"], "M001")
        self.assertIn("1 proposal(s) waiting", self.call("memory_index")[1])
        err, _ = self.call("memory_review", id="M001", decision="accept", reviewed_by="memory-manager")
        self.assertFalse(err)
        self.assertIn("[M001] (dates) Treat 2013 as the current year", self.call("memory_index")[1])

    def test_errors_come_back_as_tool_errors(self):
        err, text = self.call("memory_review", id="M999", decision="accept", reviewed_by="x")
        self.assertTrue(err)
        self.assertIn("no memory with id M999", text)
        err, text = self.call("db_query", sql="DELETE FROM Invoice")
        self.assertTrue(err)
        self.assertIn("readonly", text)
        self.assertIn("Method not found", self.send("bogus/method")["error"]["message"])

    def test_db_query(self):
        err, text = self.call("db_query", sql="SELECT COUNT(*) FROM Customer")
        self.assertFalse(err)
        self.assertEqual(json.loads(text)["rows"], [[59]])


if __name__ == "__main__":
    unittest.main()
