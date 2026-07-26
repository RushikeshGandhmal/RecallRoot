#!/usr/bin/env python3
"""Quarantine the unsafe memory and replay the latest incident."""

from _client import ServiceError, fail, print_json
from _workflow import get_incident, incident_id, remediate


def main() -> None:
    try:
        incident = get_incident()
        identifier = incident_id(incident)
        quarantined, replayed, compared = remediate(incident)
    except ServiceError as exc:
        fail(str(exc))

    print(f"Incident {identifier} remediated and replayed.")
    print("Quarantine:")
    print_json(quarantined)
    print("Replay:")
    print_json(replayed)
    print("Before/after comparison:")
    print_json(compared)


if __name__ == "__main__":
    main()
