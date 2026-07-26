#!/usr/bin/env python3
"""Create the trusted policy and Session A's unsafe durable memory."""

import argparse

from _client import ServiceError, fail, print_json
from _workflow import ingest_unsafe_memory, seed_trusted_policy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trusted-only",
        action="store_true",
        help="seed only the trusted system policy and skip Session A",
    )
    args = parser.parse_args()

    try:
        trusted = seed_trusted_policy()
        unsafe = None if args.trusted_only else ingest_unsafe_memory()
    except ServiceError as exc:
        fail(str(exc))

    print("Trusted policy seeded.")
    print_json(trusted)
    if unsafe is not None:
        print("Session A ingested the untrusted external note.")
        print_json(unsafe)


if __name__ == "__main__":
    main()
