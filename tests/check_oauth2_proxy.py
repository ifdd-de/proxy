"""Check that a rendered instance uses the oauth2-proxy values a fixture configures.

    python tests/check_oauth2_proxy.py <fixture.yaml> <rendered instance>

The instance tests only see the rendered files; here the configured values
are known, so a render that drops or changes one of them is caught:

- ifdd_proxy_oauth2_proxy_ca_file: the CA oauth2-proxy trusts;
- ifdd_proxy_oauth2_proxy_service: the Traefik service the labels declare and
  the fallback router uses; services behind the gate (ifdd-de/wf) name it
  with the same shared variable;
- ifdd_keycloak_proxy_gate_hosts: the hosts oauth2-proxy may send the
  browser back to after the login (OAUTH2_PROXY_WHITELIST_DOMAINS).
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

        slug = Path(instance).resolve().name
        name = context.get("ifdd_proxy_oauth2_proxy_service", f"{slug}-oauth2-proxy")
        labels = service.get("labels") or []
        declared = {label.split(".")[3] for label in labels if label.startswith("traefik.http.services.")}
        used = {label.split("=", 1)[1] for label in labels
                if label.startswith("traefik.http.routers.") and ".service=" in label}
        if declared != {name} or used != {name}:
            errors.append(f"Traefik service of oauth2-proxy: declared {sorted(declared)}, "
                          f"used {sorted(used)}, expected {name!r}")

        gates = [h.strip() for h in context.get("ifdd_keycloak_proxy_gate_hosts", "").split(",") if h.strip()]
        expected = ",".join(gates) if gates else None
        found = service["environment"].get("OAUTH2_PROXY_WHITELIST_DOMAINS")
        if found != expected:
            errors.append(f"OAUTH2_PROXY_WHITELIST_DOMAINS is {found!r}, expected {expected!r}")
    for error in errors:
        print(f"FAIL  {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
