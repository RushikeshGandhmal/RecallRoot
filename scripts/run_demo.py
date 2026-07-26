#!/usr/bin/env python3
"""Run either Session B alone or the complete RecallRoot repair loop."""

import argparse

from _client import ServiceError, fail, print_json
from _workflow import (
    assert_policy_violation,
    get_incident,
    incident_id,
    ingest_unsafe_memory,
    remediate,
    reset,
    seed_trusted_policy,
    submit_refund,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unsafe-only",
        action="store_true",
        help="submit Session B against already-seeded state; do not reset or remediate",
    )
    args = parser.parse_args()

    try:
        if not args.unsafe_only:
            reset()
            seed_trusted_policy()
            ingest_unsafe_memory()

        refund = submit_refund()
        preferred = incident_id(refund)
        incident = get_incident(preferred)
        assert_policy_violation(refund, incident)

        if args.unsafe_only:
            print("Unsafe Session B completed: the HTTP/tool call succeeded but policy failed.")
            print_json({"refund": refund, "incident": incident})
            return

        quarantined, replayed, compared = remediate(incident)
    except ServiceError as exc:
        fail(str(exc))

    print("RecallRoot end-to-end loop completed and the replay outcome improved.")
    print_json(
        {
            "unsafe_refund": refund,
            "incident": incident,
            "quarantine": quarantined,
            "replay": replayed,
            "comparison": compared,
        }
    )


if __name__ == "__main__":
    main()
