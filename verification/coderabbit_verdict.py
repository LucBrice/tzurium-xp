"""Validate CodeRabbit review evidence bound to one GitHub pull-request head.

The input is the unmodified JSON response from GitHub's GraphQL API.  This
module is deliberately stdlib-only so the exact same file can run in the
public mirror workflow.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Mapping, Sequence


OBJECT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
CODERABBIT_LOGINS = frozenset({"coderabbitai", "coderabbitai[bot]"})
SUBMITTED_REVIEW_STATES = frozenset(
    {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}
)


class VerdictError(ValueError):
    """Raised when the payload cannot prove an admissible current-head review."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise VerdictError(f"INCOMPLETE: {label} is missing or malformed")
    return value


def _nodes(connection: object, label: str) -> Sequence[object]:
    connection_map = _mapping(connection, label)
    page_info = _mapping(connection_map.get("pageInfo"), f"{label}.pageInfo")
    if page_info.get("hasNextPage") is not False:
        raise VerdictError(f"INCOMPLETE: {label} pagination is incomplete")
    nodes = connection_map.get("nodes")
    if not isinstance(nodes, list):
        raise VerdictError(f"INCOMPLETE: {label}.nodes is missing or malformed")
    return nodes


def evaluate_payload(
    payload: object,
    *,
    expected_head: str | None = None,
) -> dict[str, object]:
    """Return a PASS verdict or fail closed on absent, stale, or unresolved proof."""
    root = _mapping(payload, "payload")
    # A GraphQL response omits "errors" entirely when nothing went wrong
    # (spec: the field must not be present on a clean response). Checking
    # truthiness instead of presence would let a malformed-but-falsy value
    # (null, [], {}, "") through as if the field were absent.
    if "errors" in root:
        raise VerdictError("INCOMPLETE: GitHub GraphQL response contains errors")
    data = _mapping(root.get("data"), "data")
    repository = _mapping(data.get("repository"), "data.repository")
    pull_request = _mapping(
        repository.get("pullRequest"), "data.repository.pullRequest"
    )

    head = pull_request.get("headRefOid")
    if not isinstance(head, str) or OBJECT_ID.fullmatch(head) is None:
        raise VerdictError("INCOMPLETE: pull-request head SHA is missing or invalid")
    if expected_head is not None and head != expected_head:
        raise VerdictError("INCOMPLETE: GraphQL pull-request head does not match expected head")

    reviews = _nodes(pull_request.get("reviews"), "reviews")
    current_reviews = 0
    for index, raw_review in enumerate(reviews):
        review = _mapping(raw_review, f"reviews.nodes[{index}]")
        author = review.get("author")
        # GitHub returns author: null for a review whose author account was
        # deleted. That review simply cannot be the current CodeRabbit
        # review -- skip it rather than refusing the whole payload over an
        # unrelated node.
        login = author.get("login") if isinstance(author, dict) else None
        if login not in CODERABBIT_LOGINS:
            continue
        if review.get("state") not in SUBMITTED_REVIEW_STATES:
            continue
        commit = _mapping(review.get("commit"), f"reviews.nodes[{index}].commit")
        if commit.get("oid") == head:
            current_reviews += 1
    if current_reviews == 0:
        raise VerdictError("REVIEW_ABSENT_OR_STALE: no CodeRabbit review is bound to head")

    threads = _nodes(pull_request.get("reviewThreads"), "reviewThreads")
    active_unresolved = 0
    for index, raw_thread in enumerate(threads):
        thread = _mapping(raw_thread, f"reviewThreads.nodes[{index}]")
        is_resolved = thread.get("isResolved")
        is_outdated = thread.get("isOutdated")
        if not isinstance(is_resolved, bool) or not isinstance(is_outdated, bool):
            raise VerdictError(
                f"INCOMPLETE: reviewThreads.nodes[{index}] has malformed state"
            )
        if not is_resolved:
            # isOutdated only means the diff context moved under the thread,
            # never that it was resolved -- counting it out let a real
            # unresolved finding pass simply because later commits touched
            # nearby lines.
            active_unresolved += 1
    if active_unresolved:
        raise VerdictError(
            f"UNRESOLVED_THREADS: {active_unresolved} active unresolved review thread(s)"
        )

    return {
        "status": "PASS",
        "head_sha": head,
        "current_coderabbit_reviews": current_reviews,
        "active_unresolved_threads": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--expected-head")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with args.payload.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
        verdict = evaluate_payload(payload, expected_head=args.expected_head)
    except (OSError, json.JSONDecodeError, VerdictError) as exc:
        print(f"CODERABBIT_VERDICT_REFUSED: {exc}", file=__import__("sys").stderr)
        return 2
    print(json.dumps(verdict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
