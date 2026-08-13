import unittest
import sys
import types
from unittest.mock import patch

config_stub = types.ModuleType("app.config")
config_stub.get_settings = lambda: None
sys.modules.setdefault("app.config", config_stub)

from app.mailbox import gmail_message_action


class FakeMailbox:
    def __init__(self):
        self.calls = []
        self.expunged = False

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return "OK", [b"1"]

    def uid(self, *args):
        self.calls.append(("uid", *args))
        return "OK", []

    def expunge(self):
        self.expunged = True
        return "OK", []

    def logout(self):
        pass


class MailboxActionTests(unittest.TestCase):
    def test_trash_removes_inbox_and_adds_trash_label(self):
        mailbox = FakeMailbox()
        with patch("app.mailbox._connect", return_value=mailbox):
            result = gmail_message_action("42", "trash", "INBOX")
        self.assertEqual(result["action"], "trash")
        self.assertIn(("uid", "STORE", "42", "-X-GM-LABELS", "(\\Inbox)"), mailbox.calls)
        self.assertIn(("uid", "STORE", "42", "+X-GM-LABELS", "(\\Trash)"), mailbox.calls)

    def test_permanent_delete_is_restricted_to_trash(self):
        mailbox = FakeMailbox()
        with patch("app.mailbox._connect", return_value=mailbox):
            with self.assertRaisesRegex(ValueError, "only allowed from Trash"):
                gmail_message_action("42", "delete", "INBOX")
        self.assertFalse(mailbox.expunged)

    def test_permanent_delete_marks_and_expunges_trash_message(self):
        mailbox = FakeMailbox()
        with patch("app.mailbox._connect", return_value=mailbox):
            result = gmail_message_action("42", "delete", "[Gmail]/Trash")
        self.assertEqual(result["action"], "delete")
        self.assertIn(("uid", "STORE", "42", "+FLAGS", "(\\Deleted)"), mailbox.calls)
        self.assertTrue(mailbox.expunged)


if __name__ == "__main__":
    unittest.main()
