# ifdd-de/proxy

cookiecutter/cruft template for the reverse proxy in front of the IFDD
services (`ifdd-de/be`, `ifdd-de/ui` and the others on the `proxy-net`
network). The generated instance runs the upstream Traefik image with a
rendered configuration; it builds no image of its own.

## Generate an instance

```bash
cruft create --no-input --checkout <tag> \
  --config-file cookiecutter_all.yaml \
  --skip .env --skip secrets --skip certs --skip letsencrypt \
  --skip logs --skip traefik/private \
  --output-dir ../instances https://github.com/ifdd-de/proxy
```

The skip list keeps instance-owned files (secrets, keys, ACME state, the
private dynamic configuration) out of every later `cruft update`.

## Variables

| Variable | Default | Meaning |
|---|---|---|
| `ifdd_proxy_prj_name`, `ifdd_proxy_prj_slug` | `IFDD Proxy`, derived | name and directory of the instance |
| `ifdd_proxy_traefik_version` | `v3.7.16` | tag of the upstream `traefik` image |
| `ifdd_proxy_host` | `proxy` | dashboard host (default for `IFDD_PROXY_DASHBOARD_HOST` in `.env`) |
| `ifdd_proxy_dashboard_user` | `admin` | dashboard user; the post-generation hook generates its password into `.env` and `secrets/dashboard.htpasswd` |
| `ifdd_proxy_port`, `ifdd_proxy_tls_port` | `80`, `443` | host ports (defaults in `.env`) |
| `ifdd_proxy_log_level` | `WARN` | Traefik log level, production |
| `ifdd_proxy_network` | `proxy-net` | Docker network the services join |
| `ifdd_proxy_internal_hosts` | empty | comma-separated host names that containers on that network resolve to the proxy (network aliases), so services call each other under their public URLs; also the names `adm_01_certs.sh` puts into the certificate |
| `ifdd_proxy_enable_security_headers` | `y` | response-header middlewares in `headers.yml`; each service attaches them (see the page `security` of the instance documentation) |
| `ifdd_proxy_frame_options` | `SAMEORIGIN` | value of `X-Frame-Options` |
| `ifdd_proxy_referrer_policy` | `no-referrer` | value of `Referrer-Policy` |
| `ifdd_proxy_enable_hsts` | `n` | add HSTS to `security-headers` (only for HTTPS-only hosts) |
| `ifdd_proxy_hsts_seconds` | `31536000` | `max-age` when HSTS is on |
| `ifdd_proxy_csp_api` / `_csp_api_docs` / `_csp_ui` | see YAML | Content-Security-Policy per kind of host |
| `ifdd_proxy_memory_limit` | `512M` | memory limit of the container |
| `ifdd_proxy_enable_tls` | `y` | HTTPS with redirect from HTTP |
| `ifdd_proxy_tls_min_version` | `VersionTLS13` | or `VersionTLS12` |
| `ifdd_proxy_default_cert_file`, `..._key_file` | `default.crt`, `default.key` | default certificate in `certs/` (own certificates only) |
| `ifdd_proxy_enable_letsencrypt` | `n` | Let's Encrypt instead of own certificates (needs TLS) |
| `ifdd_proxy_letsencrypt_email` | `admin@example.org` | ACME account address; a placeholder, set it in `cookiecutter_all.yaml` |
| `ifdd_proxy_letsencrypt_staging` | `n` | use the staging CA |
| `ifdd_proxy_alias_headers_strategy` | `delete` | or `reject`, `keep`; for headers such as `X_Auth_User` |
| `ifdd_proxy_trusted_ips` | empty | comma-separated IPs/CIDRs of proxies in front of Traefik |
| `ifdd_proxy_enable_socket_proxy` | `n` | read-only Docker API through a socket proxy |
| `ifdd_proxy_socket_proxy_image` | `ghcr.io/tecnativa/docker-socket-proxy:v0.5.0` | image of that proxy (tag format unverified) |
| `ifdd_proxy_enable_dos_baseline` | `y` | rate and in-flight limits on the entry point |
| `ifdd_proxy_dos_*` | see `cookiecutter.json` | limits, timeouts, body size; **syntax examples, not measured values** |

The pre-generation hook rejects combinations that would render but not work:
Let's Encrypt without TLS or without an e-mail address, malformed trusted IPs,
non-numeric limits, malformed durations, malformed or repeated internal
host names, and (with oauth2-proxy) a CA file given with a path.
| `ifdd_proxy_enable_oauth2_proxy` | `n` | shared OIDC login gate (oauth2-proxy, Keycloak) for services behind the proxy; requires TLS |
| `ifdd_proxy_oauth2_proxy_image` | `quay.io/oauth2-proxy/oauth2-proxy:v7.15.5-alpine` | oauth2-proxy image; must be an `-alpine` variant (the health check needs `wget`) |
| `ifdd_proxy_oauth2_proxy_ca_file` | empty | CA certificate in `certs/` that signed the realm's certificate, e.g. `ca.crt` from `adm_01_certs.sh`; mounted alone into oauth2-proxy and trusted in addition to the system store. Empty: system store only (public certificates) |
| `ifdd_proxy_oidc_issuer` | `https://keycloak.example.org/realms/ifdd` | Keycloak realm URL (default for `IFDD_PROXY_OIDC_ISSUER`) |
| `ifdd_proxy_oidc_client_id` | `ifdd-proxy` | Keycloak client (default for `IFDD_PROXY_OIDC_CLIENT_ID`) |

## Layout

| Path | Purpose |
|---|---|
| `cookiecutter.json` | variables |
| `hooks/` | validation before, clean-up after generation (removes files the chosen options do not use, creates `.env`, generates the dashboard password) |
| `{{cookiecutter.ifdd_proxy_prj_slug}}/` | the instance, see its README |
| `tests/fixtures/` | `defaults`, `letsencrypt` (staging, socket proxy, trusted IPs, TLS 1.2, `reject`), `plain-http` (no TLS, no DoS baseline), `internal-hosts` (network aliases, certificate script), `no-headers` (security headers off) |
| `tests/check_internal_hosts.py` | used by `template-test.yml`: the host names of a fixture arrive as aliases in both compose files and in `adm_01_certs.sh` |
| `tests/check_dashboard_credentials.py` | used by `template-test.yml`: user and generated password in `.env` match `secrets/dashboard.htpasswd` (checked with openssl), file modes |
| `tests/check_docs.py`, `tests/docs/` | used by `template-test.yml`: the documentation of the instance, see below |

`.github` and `tests` inside the instance are on the copy-without-render list:
GitHub Actions expressions and shell syntax collide with Jinja.

## Documentation of the instance (`docs/`)

Every instance carries its operating documentation as Sphinx sources in
MyST Markdown, in English (`docs/en`) and German (`docs/de`), with the same
files, labels and headings in both. The pages follow the work around the
service: `index` (purpose, architecture), `setup`, `build-release`,
`operations`, `security`, `troubleshooting`, `reference`, plus `login-gate`
(oauth2-proxy). cookiecutter fills in the values of the instance, and the
pages show only what the chosen options produce. The instance README is only
an entry point that links to them.

The pages have no `conf.py` of their own: they are meant to be copied into a
Sphinx project that documents all services. That project needs `myst_parser`
and `sphinxcontrib.mermaid`. Labels start with `ifdd-proxy-`; references to
`ifdd-instances-proxy` (the instance chapter of the meta repository) resolve
only there.

Rules for editing the pages in the template:

- change both languages in the same commit;
- no Jinja syntax in examples (`{{`, `{%`, `{#`); wrap such text in
  `{% raw %}`;
- the placeholder check of the CI greps the rendered instance for the text
  `cookiecutter` followed by a dot; do not write it literally;
- a heading inside a Jinja condition must sit inside the same condition in
  both languages.

`tests/check_docs.py` checks a rendered instance: same files, labels and
headings per level in both languages, every label with the prefix, every
reference to an own label resolvable, and a Sphinx build of each language
with `-W` (configuration `tests/docs/conf.py`, versions
`tests/docs/requirements.txt`).

## CI

| Workflow | Does |
|---|---|
| `template-test.yml` | renders each fixture, checks for leftover placeholders, runs the static checks, checks and builds the documentation (`tests/check_docs.py`), validates both compose files, starts the container (development and, with own certificates, production) and probes it |
| `template-update-test.yml` | generates from the latest tag, applies the current template with `cruft update`, fails on reject files, runs the static checks |

Generated instances carry `ci.yml`: static checks, compose validation,
development smoke test, and `cruft check`/`cruft diff` as drift indicators.
There is no release workflow, because no image is built.

## Consequences for the other templates

Services behind this proxy must **not** set router `tls` labels
(`...routers.<name>.tls=true`, `...tls.certresolver=...`). A router with its
own `tls` section replaces the TLS configuration of the entry point
completely, including the Let's Encrypt resolver. Verified against Traefik
v3.7.13. The `..._enable_tls`/`..._enable_letsencrypt` switches in `be`, `ui`
and the other templates are therefore obsolete as far as labels go.

## Honesty notes

- Documentation `docs/` (2026-10-13): rendered with cookiecutter 2.7.1 for
  all seven fixtures and with the `cookiecutter_all.yaml` of the meta
  repository; `tests/check_docs.py` passes for each (Sphinx 9.1.0,
  myst-parser 5.1.0, sphinxcontrib-mermaid 2.1.1, Python 3.13), the
  placeholder check finds nothing and the instance tests pass.
  Counter-checks on a rendered copy: a heading of another level in one
  language and a reference to an unknown own label each make it fail. The
  workflow file passes actionlint 1.7.12; the workflow itself has not run.
  Content: taken from the previous instance README, `secrets/README.md`, the
  configuration files and the meta repository; what has not been tested is
  marked as such in the pages (backup and restore, Let's Encrypt, the memory
  limit, the socket proxy image, the login gate with a real Keycloak). Also
  checked (2026-10-13): one Sphinx project per language with the pages of
  all ten service templates (rendered with `cookiecutter_all.yaml`), the instance
  chapter of the meta repository and ifdd-be-core with its OpenAPI document
  builds with `-W` and no suppressed warnings, so every cross reference
  resolves; the Mermaid diagrams of all services, and of the option variants
  of the fixtures, render in headless Chromium 141.0.7390.37 (Playwright
  1.56.0, Mermaid 11.12.1 served locally).

- Internal host names and `adm_01_certs.sh` (2026-10-04): rendering with
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
- oauth2-proxy (26.10.2): verified with the oauth2-proxy 7.15.5 binary using
  exactly the environment of the rendered compose file (only
  `OAUTH2_PROXY_COOKIE_SECURE` switched off for plain HTTP), Traefik 3.7.13
  with file-provider routers equal to the labels a service sets, and a
  simulated Keycloak realm: redirect to the realm with PKCE, callback, group
  member admitted, non-member 403. Not verified: the container image, a real
  Keycloak, and the CI smoke test with the option enabled (the fixture
  `oauth2-proxy.yaml` is not in the smoke matrix: without a reachable realm
  oauth2-proxy does not start).

- oauth2-proxy and a local CA (2026-10-07): with certificates from
  `adm_01_certs.sh`, oauth2-proxy stopped at start (`x509: certificate signed
  by unknown authority` on the OIDC discovery). `ifdd_proxy_oauth2_proxy_ca_file`
  mounts that one file and sets `OAUTH2_PROXY_PROVIDER_CA_FILES` (plural; the
  singular is not read) and `OAUTH2_PROXY_USE_SYSTEM_TRUST_STORE=true`.
  Checked with the oauth2-proxy 7.15.5 binary run with exactly the
  environment of the rendered compose file, against an issuer whose
  certificate a local CA signed: fixture `oauth2-proxy-public-ca` (no CA
  file) stops with the x509 error, fixture `oauth2-proxy` (`ca.crt`) starts.
  `docker compose config` (v5.5.1) accepts the long mount syntax and keeps
  `create_host_path: false`. The new checks (`tests/check_oauth2_proxy.py`,
  the two oauth2-proxy instance tests) fail against the previous template or
  against instances with the mount or the variables removed, with all of
  `certs/` mounted, or with the short mount syntax. Not checked: what Docker
  does when the file is missing (expected: an error instead of a directory),
  the container image, a real Keycloak.

- Generated dashboard password (2026-10-08): the hook's APR1 hash equals
  `openssl passwd -apr1` (OpenSSL 3.0.13) for the same salt; Traefik v3.7.13
  (binary, the rendered `dashboard.yml` middleware) answers 200 with the
  user and password from `.env`, 401 with a wrong password and without
  credentials. Traefik also accepted bcrypt (`htpasswd -nB`, apache2-utils
  2.4.58) and `{SHA}`, and refused SHA-512 crypt (`$6$`) and plain text.
  APR1 because the standard library has no bcrypt and Python 3.13 has no
  `crypt` module. With cruft 2.16.0, `cruft update` of an instance created
  without `--skip secrets` left `secrets/dashboard.htpasswd.rej` (hidden by
  `.gitignore`); with `--skip secrets` the update was clean. The new check
  and the CI step for the user name fail against the previous template; all
  seven fixtures render and pass the check, the instance tests and
  `docker compose config` (v5.5.1). Not checked: the smoke test with the
  generated credentials (no Docker here; CI runs it), the container image.

- oauth2-proxy health check (2026-10-08): `/ready` and `/ping` of the
  oauth2-proxy 7.15.5 binary answer 200 while it runs, BusyBox 1.36.1 `wget`
  with the arguments of the health check exits 0, and 1 once oauth2-proxy is
  stopped. The Traefik v3.7.13 binary contains the log message "Filtering
  unhealthy or starting container" (Docker provider); its effect was not
  observed here. The new instance test and the CI step for a distroless image
  fail against the previous template. With cruft 2.16.0, updating an
  oauth2-proxy instance created with the distroless image stops at the
  pre-generation hook; with `--variables-to-update` for the `-alpine` image it
  goes through without reject files. Not verified: the `-alpine` image (tag
  scheme taken from the Makefile of v7.15.5) and the health check in Docker.

See the instance README. In short: configuration behaviour was verified
against the real Traefik v3.7.13 binary; the compose files, Let's Encrypt
issuance and the socket proxy image tag were not, and are covered by the CI
smoke test where possible.
