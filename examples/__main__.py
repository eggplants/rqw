"""Verify the answers of SPARQL 50 knocks with rqw."""

from __future__ import annotations

import argparse
import secrets
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass
from enum import Enum
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
from knocks import KNOCKS, Knock

from rqw import (
    AskResult,
    GraphResult,
    QueryResult,
    RqwError,
    SelectResult,
    SparqlClient,
    SparqlHttpError,
    UpdateResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# The mirror answers `429` with `Retry-After: 60` once too many queries without a LIMIT (or with an aggregate
# or a regex) went through in a short time, and most knocks are of that kind.
RATE_LIMIT_PAUSE = 60.0
RATE_LIMIT_RETRIES = 3


class Status(Enum):
    """How one knock came out when its answer was checked."""

    OK = "OK"
    EMPTY = "EMPTY"
    FAIL = "FAIL"
    XFAIL = "XFAIL"
    XPASS = "XPASS"

    @property
    def passed(self) -> bool:
        """Whether the result was the one announced."""
        return self in {Status.OK, Status.XFAIL}


@dataclass(frozen=True, kw_only=True)
class Outcome:
    """The result of throwing one knock."""

    knock: Knock
    status: Status
    detail: str
    seconds: float


def _summarize(result: QueryResult) -> tuple[int, str]:
    """Return the "size" of a result, and a summary short enough for one line."""
    match result:
        case SelectResult() as rows:
            head = (
                ", ".join(f"{name}={rows[0][name]}" for name in rows.variables if name in rows[0]) if len(rows) else ""
            )
            return len(rows), f"{len(rows)} rows" + (f" | {head[:90]}" if head else "")
        case AskResult(value=answer):
            return 1, str(answer).lower()
        case GraphResult() as graph:
            return len(graph.data), f"{len(graph.data)} bytes"
        case UpdateResult(status=status):
            return 1, f"HTTP {status}"
    msg = f"unknown result type: {type(result).__name__}"  # pragma: no cover
    raise TypeError(msg)  # pragma: no cover


def _reason(error: Exception) -> str:
    """Fold an exception into one line, with the endpoint's parser message up front: that is the part one wants."""
    if isinstance(error, SparqlHttpError):
        excerpt = " ".join(error.body.decode("utf-8", "replace").split())
        return f"{type(error).__name__} HTTP {error.status}: {excerpt[:110]}"
    return f"{type(error).__name__}: {' '.join(str(error).split())[:110]}"


def throw(client: SparqlClient, knock: Knock) -> QueryResult:
    """Run the knock's query, waiting out the endpoint's rate limit a few times before giving up.

    A comment carrying a nonce is appended so that the endpoint's cache cannot answer for the query: the mirror
    keeps a cancelled answer for a day, and would serve it for every later run.
    """
    query = knock.query + f"# {secrets.token_hex(8)}\n"
    attempts = 0
    while True:
        try:
            return client.execute(query, expect=knock.form)
        except SparqlHttpError as error:
            attempts += 1
            if error.status != HTTPStatus.TOO_MANY_REQUESTS or attempts == RATE_LIMIT_RETRIES:
                raise
            time.sleep(RATE_LIMIT_PAUSE)


def solve(knock: Knock, client: SparqlClient) -> Outcome:
    """Throw one knock and check its answer."""
    start = time.perf_counter()
    try:
        result = throw(client, knock)
    except (RqwError, httpx.HTTPError) as error:
        elapsed = time.perf_counter() - start
        status = Status.XFAIL if knock.xfail else Status.FAIL
        return Outcome(knock=knock, status=status, detail=_reason(error), seconds=elapsed)
    elapsed = time.perf_counter() - start

    size, detail = _summarize(result)
    if knock.check is not None and (complaint := knock.check(knock, result)):
        return Outcome(knock=knock, status=Status.FAIL, detail=complaint, seconds=elapsed)
    if not size and not knock.allow_empty:
        status = Status.XFAIL if knock.xfail else Status.EMPTY
        return Outcome(knock=knock, status=status, detail=detail, seconds=elapsed)
    if knock.xfail:
        return Outcome(knock=knock, status=Status.XPASS, detail=f"{detail} (was supposed to fail)", seconds=elapsed)
    return Outcome(knock=knock, status=Status.OK, detail=detail, seconds=elapsed)


def _line(outcome: Outcome, *, verbose: bool) -> str:
    """Turn one knock's result into a line."""
    knock = outcome.knock
    line = f"[{outcome.status.value}] #{knock.no:02d} > {knock.title} ({outcome.seconds:6.2f}s)"
    if outcome.status is Status.XFAIL:
        line += f"\n         expected: {knock.xfail}"
    if verbose:
        line += "\n" + "\n".join(f"         | {row}" for row in knock.query.strip().splitlines())
    return line


def _report(outcomes: Sequence[Outcome]) -> None:
    """Print the overall tally."""
    tally = {status: sum(1 for outcome in outcomes if outcome.status is status) for status in Status}
    print("===== " + " ".join(f"{status.name}={count}" for status, count in tally.items() if count) + " =====")
    failed = [outcome for outcome in outcomes if not outcome.status.passed]
    for outcome in failed:
        print(f"[{outcome.status.value}] #{outcome.knock.no:02d} - {outcome.detail}")


def _numbers(specs: Iterable[str]) -> set[int]:
    """Turn a sequence like "1-22" or "47" into a set of numbers."""
    chosen: set[int] = set()
    for spec in specs:
        start, _, end = spec.partition("-")
        chosen.update(range(int(start), int(end or start) + 1))
    return chosen


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "numbers", nargs="*", metavar="N|N-M", help="numbers of the knocks to run (default: all of them)"
    )
    parser.add_argument(
        "-t", "--timeout", type=float, default=120.0, help="time limit per knock (seconds, default: 120)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="print the query text too")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Throw the 50 knocks one after another and print how each one came out.

    One at a time, because the mirror's 20 second limit is wall-clock: knocks thrown together slow one another
    down and push each other over it.
    """
    args = _parse_args(argv)
    wanted = _numbers(args.numbers)
    knocks = [knock for knock in KNOCKS if not wanted or knock.no in wanted]
    if not knocks:
        print("no knock matches")
        return 2

    outcomes: list[Outcome] = []
    with ExitStack() as stack:
        clients = {
            endpoint: stack.enter_context(SparqlClient(endpoint, timeout=args.timeout))
            for endpoint in sorted({knock.endpoint for knock in knocks})
        }
        for knock in knocks:
            outcome = solve(knock, clients[knock.endpoint])
            outcomes.append(outcome)
            print(_line(outcome, verbose=args.verbose), flush=True)

    _report(outcomes)
    return 0 if all(outcome.status.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
