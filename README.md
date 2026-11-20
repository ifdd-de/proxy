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
| `ifdd_proxy_extra_networks` | empty | comma-separated further Docker networks the proxy joins, with the same aliases as on `ifdd_proxy_network`, for example the internal network of `ifdd-de/lab`; external, created by hand before the proxy starts. **Shared** with `ifdd-de/lab` as `ifdd_lab_network` (one entry here per lab instance) |
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
host names or gate hosts, and (with oauth2-proxy) a CA file given with a path
or a Traefik service name that does not start with the slug.
| `ifdd_proxy_enable_oauth2_proxy` | `n` | shared OIDC login gate (oauth2-proxy, Keycloak) for services behind the proxy; requires TLS |
| `ifdd_proxy_oauth2_proxy_image` | `quay.io/oauth2-proxy/oauth2-proxy:v7.15.5-alpine` | oauth2-proxy image; must be an `-alpine` variant (the health check needs `wget`) |
| `ifdd_proxy_oauth2_proxy_ca_file` | empty | CA certificate in `certs/` that signed the realm's certificate, e.g. `ca.crt` from `adm_01_certs.sh`; mounted alone into oauth2-proxy and trusted in addition to the system store. Empty: system store only (public certificates) |
| `ifdd_proxy_oidc_issuer` | `https://keycloak.example.org/realms/ifdd` | Keycloak realm URL (default for `IFDD_PROXY_OIDC_ISSUER`) |
| `ifdd_proxy_oidc_client_id` | `ifdd-proxy` | Keycloak client (default for `IFDD_PROXY_OIDC_CLIENT_ID`) |
| `ifdd_proxy_oauth2_proxy_service` | `<slug>-oauth2-proxy` | Traefik service of oauth2-proxy; **shared** with the services behind the gate (`ifdd-de/wf`), which name it as `<value>@docker`; must start with the slug |
| `ifdd_keycloak_proxy_gate_hosts` | empty | **shared** with `ifdd-de/keycloak`: comma-separated hosts behind the gate; oauth2-proxy sends the browser back to them after the login (`OAUTH2_PROXY_WHITELIST_DOMAINS`). Empty: back to `/` of the host |

## Layout

| Path | Purpose |
|---|---|
| `cookiecutter.json` | variables |
| `hooks/` | validation before, clean-up after generation (removes files the chosen options do not use, creates `.env`, generates the dashboard password) |
| `{{cookiecutter.ifdd_proxy_prj_slug}}/` | the instance, see its README |
| `tests/fixtures/` | `defaults`, `letsencrypt` (staging, socket proxy, trusted IPs, TLS 1.2, `reject`), `plain-http` (no TLS, no DoS baseline), `internal-hosts` (network aliases, certificate script), `no-headers` (security headers off), `oauth2-proxy`, `oauth2-proxy-public-ca`, `multi-server` (one of several servers: the realm on another host, own service name, gate hosts, a CA bundle) |
| `tests/check_internal_hosts.py` | used by `template-test.yml`: the host names of a fixture arrive as aliases in both compose files and in `adm_01_certs.sh` |
| `tests/check_oauth2_proxy.py` | used by `template-test.yml`: CA file, Traefik service name and gate hosts of a fixture arrive in the oauth2-proxy service |
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
and `sphinxcontrib.plantuml` (PlantUML with Java and Graphviz).
Labels start with `ifdd-proxy-`; references to
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

The check runs PlantUML, so it needs Java and Graphviz.
`tests/docs/get_plantuml.sh` downloads the pinned PlantUML jar into the user
cache, checks its SHA-256 and prints its path:

```bash
export IFDD_PLANTUML_JAR="$(tests/docs/get_plantuml.sh)"
```

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

## AI assistance

Some parts of this repository, in particular the tests, the test data and the
documentation, were developed or improved with the help of large language
models (LLMs). All changes were reviewed and released by the maintainer.
