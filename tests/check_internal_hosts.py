"""Check that a rendered instance carries the internal host names of a fixture.

    python tests/check_internal_hosts.py <fixture.yaml> <rendered instance>

The instance tests compare the files of an instance with each other; only
here is the configured value known, so only here can a render that drops it
be caught.
"""

import re
import sys
from pathlib import Path

import yaml


def main(fixture, instance):
    context = yaml.safe_load(Path(fixture).read_text())["default_context"]
    expected = [h.strip() for h in context.get("ifdd_proxy_internal_hosts", "").split(",") if h.strip()]
    errors = []
    for compose_file in ("docker-compose-production.yml", "docker-compose-development.yml"):
        networks = yaml.safe_load((Path(instance) / compose_file).read_text())["services"]["proxy"]["networks"]
        aliases = [] if isinstance(networks, list) else (networks["proxy"] or {}).get("aliases", [])
        if aliases != expected:
            errors.append(f"{compose_file}: aliases {aliases}, expected {expected}")
    script = Path(instance) / "adm_01_certs.sh"
    if script.exists():
        match = re.search(r'^INTERNAL_HOSTS="(.*)"$', script.read_text(), re.MULTILINE)
        found = match.group(1).split() if match else None
        if found != expected:
            errors.append(f"adm_01_certs.sh: INTERNAL_HOSTS {found}, expected {expected}")
    for error in errors:
        print(f"FAIL  {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
