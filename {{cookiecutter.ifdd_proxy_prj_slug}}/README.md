# {{ cookiecutter.ifdd_proxy_prj_name }}
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}

Reverse proxy for the IFDD services, generated from the `ifdd-de/proxy`
template. Runs the upstream image `traefik:{{ cookiecutter.ifdd_proxy_traefik_version }}` on the Docker
network `{{ cookiecutter.ifdd_proxy_network }}`; services join that network and announce themselves with
labels.

This instance: TLS **{{ "on" if tls else "off" }}**{% if tls %}, certificates from **{{ "Let's Encrypt" if le else "certs/ (own certificates)" }}**{% endif %},
DoS baseline **{{ "on" if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" else "off" }}**,
socket proxy **{{ "on" if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" else "off" }}**,
login gate **{{ "on" if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" else "off" }}**.

## Quick start

```bash
docker network create {{ cookiecutter.ifdd_proxy_network }}   # once per host, if it does not exist yet
{%- if tls and not le %}
./adm_01_certs.sh                     # only without certificates of your own
{%- endif %}
docker compose -f docker-compose-production.yml up -d
docker compose -f docker-compose-production.yml ps
```

The dashboard is at `{{ "https" if tls else "http" }}://<IFDD_PROXY_DASHBOARD_HOST>/dashboard/`
(with the trailing slash); the login is `IFDD_PROXY_DASHBOARD_USER` and
`IFDD_PROXY_DASHBOARD_PASSWORD` in `.env`. Services must not set router `tls`
labels.

## Documentation

Setup, build and release, operations, security, troubleshooting, reference
and the login gate of this instance:

- English: [docs/en/index.md](docs/en/index.md)
- Deutsch: [docs/de/index.md](docs/de/index.md)

The pages are Sphinx sources in MyST Markdown, meant to be copied into a
documentation project that covers all services; GitHub shows them as plain
Markdown.

## Honesty notes

Checked against the real Traefik v3.7.13 binary (not in Docker): static and
dynamic configuration load without errors; Traefik logs one warning at
startup, that it can reject some encoded characters in request paths (checked
2026-10-04); redirect, dashboard
authentication, health check, TLS minimum version, `sniStrict`, certificate
selection by server name, `.dist` files being ignored, aliasing headers,
rate limit, opt-in buffering, resolver inheritance from the entry point, and
removal of forged `X-Forwarded-For`.

csp-api-docs without CDN (2026-10-13): ifdd-be-core serves Swagger UI and
ReDoc itself and its pages have no inline script; the default lost the CDN,
Google Fonts and fastapi.tiangolo.com and gained `worker-src 'self' blob:`.
Checked in headless Chromium (Playwright 1.56.0) behind Traefik v3.7.13 with
this rendered `headers.yml` (value from `cookiecutter_all.yaml`, realm origin
in `connect-src`), the Keycloak 26.8.0 distribution and ifdd-be-core: no
violation except ReDoc's logo from `cdn.redoc.ly`, which stays blocked;
"Authorize" and "Try it out" work. Without the realm origin the token fetch
is refused; without `worker-src` ReDoc's search finds nothing; without
`'unsafe-inline'` in `style-src` ReDoc's styles are refused. Details in the
README of ifdd-be-core.

CSP fix (2026-10-05): Keycloak now uses security-headers only (its own CSP passes through), and csp-ui allows the OIDC and backend origins in connect-src plus the OIDC endpoint in frame-src. Checked with the Traefik binary: a request to the UI host carries connect-src with id and rest, and a backend that sets its own CSP keeps it when only security-headers is attached. Not checked: the actual browser login (no browser here).

Security headers (2026-10-05): checked with the real Traefik v3.7.13 binary
(file provider, the same router middlewares the service labels set) behind the
rendered certificate: a request to the backend host carries the nosniff,
X-Frame-Options (SAMEORIGIN), Referrer-Policy and the csp-api-docs CSP, the UI
host carries csp-ui, a static JSON host carries csp-api, and the upstream
`Server` header is gone in every case. Not checked: whether the csp-ui policy
lets react-admin run (no browser here) -- verify in the browser console.

Internal host names and `adm_01_certs.sh` (2026-10-04): rendering with
cookiecutter 2.7.1 (all fixtures, plus socket proxy with aliases);
`docker compose config` (Compose v5.5.1) accepts both compose files; the
script, run with OpenSSL 3.0.13, creates a chain that verifies, covers the
internal hosts and the dashboard host, writes keys with mode 0600 and
refuses a second run without changing anything. End to end with the real
Traefik v3.7.13 binary (rendered production configuration, file provider
instead of the Docker labels), the script's certificate with `sniStrict` on,
the real Keycloak 26.8.0 distribution and the be backend: Python clients
that trust only `certs/ca.crt` reach `https://id`, `https://rest` and
`https://schema` (single-label names in SNI and SAN work). Not verified:
name resolution through Docker network aliases (no Docker available), and
browsers with the CA imported.

Generated dashboard password (2026-10-08): the APR1 line in
`secrets/dashboard.htpasswd` matches `openssl passwd -apr1` for the password
in `.env`; Traefik v3.7.13 (binary) accepts it (200), refuses a wrong password
and anonymous requests (401). Not checked in Docker here; `tests/smoke.sh`
logs in with these credentials.

oauth2-proxy health check (2026-10-08): with the oauth2-proxy 7.15.5 binary
against an issuer behind a local CA, `/ready` and `/ping` answer 200 while it
runs; BusyBox 1.36.1 `wget -q -O /dev/null http://127.0.0.1:4180/ready`
exits 0, and 1 once oauth2-proxy is stopped; without a reachable issuer
oauth2-proxy exits with status 1. Not verified: the `-alpine` image itself
(registry not reachable here; the tag scheme `<version>-alpine` and the base
`alpine:3.24.1` are from the Makefile of the v7.15.5 tag) and the health
check in Docker.

Not verified:

- The compose files themselves (`docker compose` was not available when the
  template was built); `tests/smoke.sh` in CI covers this.
- Issuance by Let's Encrypt (no access to the ACME servers during the build).
- The tag format of the socket proxy image (`{{ cookiecutter.ifdd_proxy_socket_proxy_image }}`);
  Tecnativa documents tags per released version but the exact spelling was not
  checked. With SELinux the socket proxy may need `privileged: true`.
- The reload behaviour of the file provider with Docker bind mounts.
- The client address behind Docker's userland proxy (see the DoS baseline in
  `docs/en/operations.md`).

## License

BSD-3-Clause, see `LICENSE`.
