"""Run with: python3 -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import redact  # noqa: E402  pylint: disable=wrong-import-position

NODE_IPS = "node1 203.0.113.1\nnode2   203.0.113.11\n"


class RedactTest(unittest.TestCase):
    def test_parse_node_ips(self):
        self.assertEqual(
            redact.parse_node_ips(NODE_IPS),
            {"node1": "203.0.113.1", "node2": "203.0.113.11"},
        )
        self.assertEqual(redact.parse_node_ips(""), {})

    def test_addresses_and_port_are_replaced(self):
        text = "connect to host 203.0.113.11 port 41922: refused; peer https://203.0.113.1:2380 api :50123"
        self.assertEqual(
            redact.redact(text, redact.parse_node_ips(NODE_IPS), ["41922", "50123"]),
            "connect to host [node2-address] port ***: refused; peer https://[node1-address]:2380 api :***",
        )

    def test_other_numbers_are_kept(self):
        text = "size 1419220 at 10.203.0.113.1 and 203.0.113.100"
        self.assertEqual(redact.redact(text, redact.parse_node_ips(NODE_IPS), ["41922", ""]), text)

    def test_directory_is_cleaned_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            nested = Path(directory, "health", "node.json")
            nested.parent.mkdir()
            nested.write_text('{"endpoint": "https://203.0.113.1:2379"}', encoding="utf-8")
            os.environ["NODE_IPS"], os.environ["SSH_PORT"] = NODE_IPS, ""
            os.environ["K8S_API_PORT"] = ""
            sys.argv = ["redact.py", directory]
            redact.main()
            self.assertEqual(
                nested.read_text(encoding="utf-8"), '{"endpoint": "https://[node1-address]:2379"}'
            )


if __name__ == "__main__":
    unittest.main()
