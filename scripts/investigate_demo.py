#!/usr/bin/env python3
"""Ask RecallRoot to investigate the latest policy-violation incident."""

from _client import ServiceError, fail, print_json
from _workflow import get_incident, incident_id, investigate


def main() -> None:
    try:
        incident = get_incident()
        identifier = incident_id(incident)
        if not identifier:
            raise ServiceError("RecallRoot API", "incident response is missing an ID")
        result = investigate(identifier)
    except ServiceError as exc:
        fail(str(exc))

    print(f"Investigation for {identifier}:")
    print_json(result)


if __name__ == "__main__":
    main()
