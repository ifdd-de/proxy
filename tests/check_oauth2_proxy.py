"""Check that a rendered instance trusts the CA file a fixture configures.

    python tests/check_oauth2_proxy.py <fixture.yaml> <rendered instance>

The instance tests only see the rendered files; here the configured value
ifdd_proxy_oauth2_proxy_ca_file is known, so a render that drops or changes
it is caught.
"""

import sys
from pathlib import Path

import yaml


def main(fixture, instance):
    context = yaml.safe_load(Path(fixture).read_text())["default_context"]
    compose = yaml.safe_load((Path(instance) / "docker-compose-production.yml").read_text())
    service = compose["services"].get("oauth2-proxy")
    errors = []
    if context.get("ifdd_proxy_enable_oauth2_proxy") != "y":
        if service is not None:
            errors.append("oauth2-proxy rendered although the fixture does not enable it")
    elif service is None:
        errors.append("oauth2-proxy missing although the fixture enables it")
    else:
        ca_file = context.get("ifdd_proxy_oauth2_proxy_ca_file", "")
        expected = f"/certs/{ca_file}" if ca_file else None
        found = service["environment"].get("OAUTH2_PROXY_PROVIDER_CA_FILES")
        if found != expected:
            errors.append(f"OAUTH2_PROXY_PROVIDER_CA_FILES is {found!r}, expected {expected!r}")
    for error in errors:
        print(f"FAIL  {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
