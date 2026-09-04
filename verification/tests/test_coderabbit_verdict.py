from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "coderabbit_verdict.py"
SPEC = importlib.util.spec_from_file_location("coderabbit_verdict", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
coderabbit_verdict = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coderabbit_verdict)

HEAD = "a" * 40


def green_payload() -> dict[str, object]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "headRefOid": HEAD,
                    "reviews": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [
                            {
                                "author": {"login": "coderabbitai[bot]"},
                                "state": "COMMENTED",
                                "commit": {"oid": HEAD},
                            }
                        ],
                    },
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [],
                    },
                }
            }
        }
    }


class TestCodeRabbitVerdict(unittest.TestCase):
    def test_current_commented_review_and_zero_active_threads_pass(self) -> None:
        verdict = coderabbit_verdict.evaluate_payload(
            green_payload(), expected_head=HEAD
        )
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["current_coderabbit_reviews"], 1)

    def test_stale_review_is_refused(self) -> None:
        payload = copy.deepcopy(green_payload())
        payload["data"]["repository"]["pullRequest"]["reviews"]["nodes"][0]["commit"]["oid"] = "b" * 40
        with self.assertRaisesRegex(
            coderabbit_verdict.VerdictError, "REVIEW_ABSENT_OR_STALE"
        ):
            coderabbit_verdict.evaluate_payload(payload)

    def test_absent_review_is_refused(self) -> None:
        payload = copy.deepcopy(green_payload())
        payload["data"]["repository"]["pullRequest"]["reviews"]["nodes"] = []
        with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "ABSENT"):
            coderabbit_verdict.evaluate_payload(payload)

    def test_dismissed_or_pending_review_is_refused(self) -> None:
        for state in ("DISMISSED", "PENDING"):
            with self.subTest(state=state):
                payload = copy.deepcopy(green_payload())
                payload["data"]["repository"]["pullRequest"]["reviews"]["nodes"][0]["state"] = state
                with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "ABSENT"):
                    coderabbit_verdict.evaluate_payload(payload)

    def test_null_author_review_is_skipped_not_refused(self) -> None:
        payload = copy.deepcopy(green_payload())
        payload["data"]["repository"]["pullRequest"]["reviews"]["nodes"].insert(
            0, {"author": None, "state": "COMMENTED", "commit": {"oid": HEAD}}
        )
        verdict = coderabbit_verdict.evaluate_payload(payload, expected_head=HEAD)
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["current_coderabbit_reviews"], 1)

    def test_null_commit_review_is_skipped_not_refused(self) -> None:
        payload = copy.deepcopy(green_payload())
        payload["data"]["repository"]["pullRequest"]["reviews"]["nodes"].insert(
            0, {"author": {"login": "coderabbitai[bot]"}, "state": "COMMENTED", "commit": None}
        )
        verdict = coderabbit_verdict.evaluate_payload(payload, expected_head=HEAD)
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["current_coderabbit_reviews"], 1)

    def test_active_unresolved_thread_is_refused(self) -> None:
        payload = copy.deepcopy(green_payload())
        payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"] = [
            {"isResolved": False, "isOutdated": False}
        ]
        with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "UNRESOLVED"):
            coderabbit_verdict.evaluate_payload(payload)

    def test_outdated_unresolved_thread_is_still_active(self) -> None:
        payload = copy.deepcopy(green_payload())
        payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"] = [
            {"isResolved": False, "isOutdated": True}
        ]
        with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "UNRESOLVED"):
            coderabbit_verdict.evaluate_payload(payload)

    def test_outdated_but_resolved_thread_is_not_active(self) -> None:
        payload = copy.deepcopy(green_payload())
        payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"] = [
            {"isResolved": True, "isOutdated": True}
        ]
        verdict = coderabbit_verdict.evaluate_payload(payload, expected_head=HEAD)
        self.assertEqual(verdict["status"], "PASS")

    def test_malformed_thread_state_is_refused(self) -> None:
        for node in (
            {"isResolved": None, "isOutdated": False},
            {"isResolved": False},
            {"isResolved": "false", "isOutdated": False},
        ):
            with self.subTest(node=node):
                payload = copy.deepcopy(green_payload())
                payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"] = [node]
                with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "malformed state"):
                    coderabbit_verdict.evaluate_payload(payload, expected_head=HEAD)

    def test_invalid_head_ref_oid_is_refused(self) -> None:
        for head in (None, "", "z" * 40, "a" * 39, 40):
            with self.subTest(head=head):
                payload = copy.deepcopy(green_payload())
                payload["data"]["repository"]["pullRequest"]["headRefOid"] = head
                with self.assertRaisesRegex(
                    coderabbit_verdict.VerdictError, "head SHA is missing or invalid"
                ):
                    coderabbit_verdict.evaluate_payload(payload, expected_head=HEAD)

    def test_missing_containers_are_refused(self) -> None:
        for path in (["data"], ["data", "repository"], ["data", "repository", "pullRequest"]):
            with self.subTest(path=path):
                payload = copy.deepcopy(green_payload())
                target = payload
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = None
                with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "missing or malformed"):
                    coderabbit_verdict.evaluate_payload(payload, expected_head=HEAD)

    def test_malformed_nodes_list_is_refused(self) -> None:
        for connection in ("reviews", "reviewThreads"):
            with self.subTest(connection=connection):
                payload = copy.deepcopy(green_payload())
                payload["data"]["repository"]["pullRequest"][connection]["nodes"] = None
                with self.assertRaisesRegex(
                    coderabbit_verdict.VerdictError, "nodes is missing or malformed"
                ):
                    coderabbit_verdict.evaluate_payload(payload, expected_head=HEAD)

    def test_cli_refusal_returns_exit_code_two(self) -> None:
        payload = copy.deepcopy(green_payload())
        payload["data"]["repository"]["pullRequest"]["reviews"]["nodes"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            code = coderabbit_verdict.main(["--payload", str(path), "--expected-head", HEAD])
        self.assertEqual(code, 2)

    def test_missing_expected_head_never_passes(self) -> None:
        with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "expected_head is required"):
            coderabbit_verdict.evaluate_payload(green_payload())

    def test_any_incomplete_pagination_is_refused(self) -> None:
        for connection in ("reviews", "reviewThreads"):
            with self.subTest(connection=connection):
                payload = copy.deepcopy(green_payload())
                payload["data"]["repository"]["pullRequest"][connection]["pageInfo"]["hasNextPage"] = True
                with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "pagination"):
                    coderabbit_verdict.evaluate_payload(payload)

    def test_expected_head_mismatch_is_refused(self) -> None:
        with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "expected head"):
            coderabbit_verdict.evaluate_payload(green_payload(), expected_head="b" * 40)

    def test_graphql_errors_are_refused(self) -> None:
        payload = green_payload()
        payload["errors"] = [{"message": "partial result"}]
        with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "contains errors"):
            coderabbit_verdict.evaluate_payload(payload)

    def test_falsy_but_present_errors_field_is_still_refused(self) -> None:
        for falsy_errors in (None, [], {}, "", 0):
            with self.subTest(falsy_errors=falsy_errors):
                payload = green_payload()
                payload["errors"] = falsy_errors
                with self.assertRaisesRegex(coderabbit_verdict.VerdictError, "contains errors"):
                    coderabbit_verdict.evaluate_payload(payload)


if __name__ == "__main__":
    unittest.main()
