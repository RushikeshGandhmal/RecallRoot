#!/usr/bin/env python3
"""Reset the deterministic local RecallRoot scenario."""

from _client import ServiceError, fail, print_json
from _workflow import reset


def main() -> None:
    try:
        response = reset()
    except ServiceError as exc:
        fail(str(exc))
    print("RecallRoot demo state reset.")
    print_json(response)


if __name__ == "__main__":
    main()
