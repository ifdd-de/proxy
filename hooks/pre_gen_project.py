"""Reject configurations that would render but could not work.

Everything checked here fails later and less clearly otherwise: Traefik logs
an error and keeps running with a partial configuration.
"""

import ipaddress
import re
import sys

PROJECT_SLUG_REGEX = r"^[_a-zA-Z][_a-zA-Z0-9-]+$"
DURATION_REGEX = r"^[0-9]+(ms|s|m|h)$"
HOST_REGEX = r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$"

project_slug = "{{ cookiecutter.ifdd_proxy_prj_slug }}"
enable_tls = "{{ cookiecutter.ifdd_proxy_enable_tls }}"
enable_letsencrypt = "{{ cookiecutter.ifdd_proxy_enable_letsencrypt }}"
letsencrypt_email = "{{ cookiecutter.ifdd_proxy_letsencrypt_email }}"
trusted_ips = "{{ cookiecutter.ifdd_proxy_trusted_ips }}"
enable_dos = "{{ cookiecutter.ifdd_proxy_enable_dos_baseline }}"
internal_hosts = "{{ cookiecutter.ifdd_proxy_internal_hosts }}"
oauth2_proxy_ca_file = "{{ cookiecutter.ifdd_proxy_oauth2_proxy_ca_file }}"
dashboard_user = "{{ cookiecutter.ifdd_proxy_dashboard_user }}"

yes_no = {
    "ifdd_proxy_enable_tls": enable_tls,
    "ifdd_proxy_enable_letsencrypt": enable_letsencrypt,
    "ifdd_proxy_letsencrypt_staging": "{{ cookiecutter.ifdd_proxy_letsencrypt_staging }}",
    "ifdd_proxy_enable_socket_proxy": "{{ cookiecutter.ifdd_proxy_enable_socket_proxy }}",
    "ifdd_proxy_enable_dos_baseline": enable_dos,
    "ifdd_proxy_dos_enable_buffering": "{{ cookiecutter.ifdd_proxy_dos_enable_buffering }}",
    "ifdd_proxy_enable_oauth2_proxy": "{{ cookiecutter.ifdd_proxy_enable_oauth2_proxy }}",
}

enable_oauth2_proxy = "{{ cookiecutter.ifdd_proxy_enable_oauth2_proxy }}"
oidc_issuer = "{{ cookiecutter.ifdd_proxy_oidc_issuer }}"
oidc_client_id = "{{ cookiecutter.ifdd_proxy_oidc_client_id }}"
oauth2_proxy_image = "{{ cookiecutter.ifdd_proxy_oauth2_proxy_image }}"

positive_integers = {
    "ifdd_proxy_port": "{{ cookiecutter.ifdd_proxy_port }}",
    "ifdd_proxy_tls_port": "{{ cookiecutter.ifdd_proxy_tls_port }}",
    "ifdd_proxy_dos_rate_average": "{{ cookiecutter.ifdd_proxy_dos_rate_average }}",
    "ifdd_proxy_dos_rate_burst": "{{ cookiecutter.ifdd_proxy_dos_rate_burst }}",
    "ifdd_proxy_dos_inflight_amount": "{{ cookiecutter.ifdd_proxy_dos_inflight_amount }}",
    "ifdd_proxy_dos_ipv6_subnet": "{{ cookiecutter.ifdd_proxy_dos_ipv6_subnet }}",
    "ifdd_proxy_dos_max_request_body_bytes": "{{ cookiecutter.ifdd_proxy_dos_max_request_body_bytes }}",
    "ifdd_proxy_dos_mem_request_body_bytes": "{{ cookiecutter.ifdd_proxy_dos_mem_request_body_bytes }}",
    "ifdd_proxy_dos_max_header_bytes": "{{ cookiecutter.ifdd_proxy_dos_max_header_bytes }}",
    "ifdd_proxy_dos_h2_max_streams": "{{ cookiecutter.ifdd_proxy_dos_h2_max_streams }}",
}

durations = {
    "ifdd_proxy_dos_rate_period": "{{ cookiecutter.ifdd_proxy_dos_rate_period }}",
    "ifdd_proxy_dos_read_timeout": "{{ cookiecutter.ifdd_proxy_dos_read_timeout }}",
    "ifdd_proxy_dos_write_timeout": "{{ cookiecutter.ifdd_proxy_dos_write_timeout }}",
    "ifdd_proxy_dos_idle_timeout": "{{ cookiecutter.ifdd_proxy_dos_idle_timeout }}",
}

errors = []

if not re.match(PROJECT_SLUG_REGEX, project_slug):
    errors.append(f"{project_slug} is not a valid project slug")

for name, value in yes_no.items():
    if value not in ("y", "n"):
        errors.append(f"{name} must be 'y' or 'n', got {value!r}")

for name, value in positive_integers.items():
    if not value.isdigit() or int(value) <= 0:
        errors.append(f"{name} must be a positive integer, got {value!r}")

if enable_dos == "y":
    for name, value in durations.items():
        if not re.match(DURATION_REGEX, value):
            errors.append(f"{name} must be a duration such as 15s, got {value!r}")

# One "user:hash" line per user in secrets/dashboard.htpasswd: no colon, no
# whitespace, nothing that needs quoting in .env.
if not re.fullmatch(r"[A-Za-z0-9_.@-]+", dashboard_user):
    errors.append(f"ifdd_proxy_dashboard_user: letters, digits, '_', '.', '@', '-' only, got {dashboard_user!r}")

if enable_letsencrypt == "y" and enable_tls != "y":
    errors.append("ifdd_proxy_enable_letsencrypt=y requires ifdd_proxy_enable_tls=y")

if enable_letsencrypt == "y" and "@" not in letsencrypt_email:
    errors.append("ifdd_proxy_letsencrypt_email must be an e-mail address when Let's Encrypt is enabled")

for entry in (part.strip() for part in trusted_ips.split(",") if part.strip()):
    try:
        ipaddress.ip_network(entry, strict=False)
    except ValueError:
        errors.append(f"ifdd_proxy_trusted_ips: {entry!r} is neither an IP address nor a CIDR range")

hosts = [part.strip() for part in internal_hosts.split(",") if part.strip()]
if not all(re.match(HOST_REGEX, host) for host in hosts) or len(set(hosts)) != len(hosts):
    errors.append(
        "ifdd_proxy_internal_hosts: comma-separated, distinct host names without scheme, "
        f"port or path, got {internal_hosts!r}"
    )

if enable_oauth2_proxy == "y":
    if not re.fullmatch(r"https?://[^\s/]+(/[^\s]*)?", oidc_issuer) or oidc_issuer.endswith("/"):
        errors.append(f"ifdd_proxy_oidc_issuer must be the realm URL without trailing slash, got {oidc_issuer!r}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", oidc_client_id):
        errors.append(f"ifdd_proxy_oidc_client_id must be a Keycloak client id, got {oidc_client_id!r}")
    # The health check runs wget inside the container. The default images are
    # distroless (no shell, no wget): the check would always fail, and Traefik
    # ignores containers that are not healthy.
    if not oauth2_proxy_image.endswith("-alpine"):
        errors.append(
            "ifdd_proxy_oauth2_proxy_image must be an -alpine variant (its health check needs wget), "
            f"got {oauth2_proxy_image!r}"
        )
    if enable_tls != "y":
        # The session cookie is marked Secure; browsers drop it on plain HTTP.
        errors.append("ifdd_proxy_enable_oauth2_proxy=y requires ifdd_proxy_enable_tls=y")
    # A file in certs/, mounted on its own: a path could reach the private
    # keys next to it or leave the instance.
    if oauth2_proxy_ca_file and (
        not re.fullmatch(r"[A-Za-z0-9_.-]+", oauth2_proxy_ca_file) or oauth2_proxy_ca_file in (".", "..")
    ):
        errors.append(
            "ifdd_proxy_oauth2_proxy_ca_file must be a file name in certs/ without a path, "
            f"got {oauth2_proxy_ca_file!r}"
        )

if errors:
    for error in errors:
        print(f"ERROR: {error}")
    sys.exit(1)
