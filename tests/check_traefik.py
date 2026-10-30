"""Check that the Traefik names of a rendered instance follow its slug.

    python tests/check_traefik.py <rendered instance>

Every router, service and middleware the labels of the compose files declare
is named "<slug>-<role>" (e.g. "<slug>-dashboard", "<slug>-oauth2-proxy"),
so that the names do not collide with those of other instances on the same
Docker host. The slug is the name of the rendered directory.
"""

import re
import sys
from pathlib import Path

import yaml

NAME = re.compile(r"^traefik\.http\.(routers|services|middlewares)\.([^.]+)\.")


def main(instance):
    slug = Path(instance).resolve().name
    errors = []
    for compose_file in ("docker-compose-production.yml", "docker-compose-development.yml"):
        compose = yaml.safe_load((Path(instance) / compose_file).read_text())
        for service_name, service in compose["services"].items():
            for label in service.get("labels") or []:
                match = NAME.match(label)
                if match and not match[2].startswith(slug + "-"):
                    errors.append(f"{compose_file}: {service_name}: {match[1]} name {match[2]!r} "
                                  f"does not start with the slug {slug + '-'!r}: {label}")
    for error in errors:
        print(f"FAIL  {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
