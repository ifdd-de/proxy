"""Check the dashboard credentials the post-generation hook creates.

    python tests/check_dashboard_credentials.py <fixture.yaml> <rendered instance>

The hook generates a password into .env and writes the matching APR1 line to
secrets/dashboard.htpasswd. The hash is checked with openssl, independently
of the hook's own implementation. tests/smoke.sh then logs in with it.
"""

import stat
import subprocess
import sys
from pathlib import Path

import yaml


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def apr1_matches(line, user, password):
    """user:$apr1$<salt>$<hash>, with the hash openssl computes for password."""
    name, _, hashed = line.partition(":")
    parts = hashed.split("$")  # "", "apr1", salt, hash
    if name != user or len(parts) != 4 or parts[1] != "apr1":
        return False
    result = subprocess.run(
        ["openssl", "passwd", "-apr1", "-salt", parts[2], "-stdin"],
        input=password,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip() == hashed


def main(fixture, instance):
    context = yaml.safe_load(Path(fixture).read_text())["default_context"]
    user = context.get("ifdd_proxy_dashboard_user", "admin")
    root = Path(instance)
    env = dict(
        line.split("=", 1) for line in (root / ".env").read_text().splitlines() if line and not line.startswith("#")
    )
    htpasswd = root / "secrets" / "dashboard.htpasswd"
    errors = []
    password = env.get("IFDD_PROXY_DASHBOARD_PASSWORD", "")
    if env.get("IFDD_PROXY_DASHBOARD_USER") != user:
        errors.append(f"IFDD_PROXY_DASHBOARD_USER is {env.get('IFDD_PROXY_DASHBOARD_USER')!r}, expected {user!r}")
    if len(password) != 32 or not password.isalnum():
        errors.append("IFDD_PROXY_DASHBOARD_PASSWORD is not 32 letters and digits")
    if not htpasswd.is_file():
        errors.append("secrets/dashboard.htpasswd is missing")
    else:
        lines = htpasswd.read_text().splitlines()
        if len(lines) != 1 or not apr1_matches(lines[0], user, password):
            errors.append("secrets/dashboard.htpasswd is not one APR1 line for the user and password in .env")
        if mode(htpasswd) != 0o644 or mode(root / "secrets") != 0o700:
            errors.append("expected mode 0644 for secrets/dashboard.htpasswd and 0700 for secrets/")
    if mode(root / ".env") != 0o600:
        errors.append(".env holds the dashboard password but is not mode 0600")
    for error in errors:
        print(f"FAIL  {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
