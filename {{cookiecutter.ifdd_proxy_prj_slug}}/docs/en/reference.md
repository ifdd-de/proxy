(ifdd-proxy-reference)=
# Reference
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set own = tls and not le %}
{%- set sp = cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
{%- set o2 = cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

The variables of the template and their values in this instance are listed
in {ref}`ifdd-instances-proxy`. This page lists what is not a template
variable.

## Layout

| Path | Purpose |
|---|---|
| `traefik/traefik.yml` | static configuration, production (the only source: no CLI flags, no `TRAEFIK_*` variables) |
| `traefik/traefik.development.yml` | static configuration, local development |
| `traefik/dynamic/shared/` | dashboard authentication{% if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" %}, DoS baseline{% endif %}{% if cookiecutter.ifdd_proxy_enable_security_headers == "y" %}, security headers{% endif %} |
{%- if tls %}
| `traefik/dynamic/production/`, `traefik/dynamic/development/` | TLS options per environment |
{%- endif %}
| `traefik/private/` | instance-specific dynamic configuration (further certificates, routers); every `*.yml` is loaded in production |
| `secrets/` | `dashboard.htpasswd`{% if o2 %}, `oauth2_proxy_cookie_secret`, `oauth2_proxy_client_secret`{% endif %}; git-ignored |
{%- if own %}
| `certs/` | own certificates and keys, git-ignored |
| `adm_01_certs.sh` | local CA and default certificate, once |
{%- endif %}
{%- if le %}
| `letsencrypt/` | ACME account and certificates (`acme.json`), git-ignored |
{%- endif %}
| `logs/` | access log |
| `dotenv.dist` → `.env` | values for the compose files |
| `tests/` | static checks and smoke test |

## Environment (`.env`)

Read by Docker Compose for the `${...}` of the compose files only; not
passed into any container except where noted.

| Variable | Default here | Meaning |
|---|---|---|
| `IFDD_PROXY_DASHBOARD_HOST` | `{{ cookiecutter.ifdd_proxy_host }}` | host of the dashboard router (paths `/dashboard`, `/api`) |
| `IFDD_PROXY_DASHBOARD_USER` | `{{ cookiecutter.ifdd_proxy_dashboard_user }}` | for reading only; Traefik checks `secrets/dashboard.htpasswd` |
| `IFDD_PROXY_DASHBOARD_PASSWORD` | generated | for reading only |
| `IFDD_PROXY_HTTP_PORT` | `{{ cookiecutter.ifdd_proxy_port }}` | host port for HTTP |
| `IFDD_PROXY_HTTPS_PORT` | `{{ cookiecutter.ifdd_proxy_tls_port }}` | host port for HTTPS{% if not tls %} (unused: TLS is off){% endif %} |
{%- if o2 %}
| `IFDD_PROXY_OIDC_ISSUER` | `{{ cookiecutter.ifdd_proxy_oidc_issuer }}` | realm URL; passed to oauth2-proxy |
| `IFDD_PROXY_OIDC_CLIENT_ID` | `{{ cookiecutter.ifdd_proxy_oidc_client_id }}` | client of oauth2-proxy; passed to oauth2-proxy |
{%- endif %}

## Entry points, ports and networks

| Entry point | Address | Use |
|---|---|---|
| `web` | `:80`, host port `{{ cookiecutter.ifdd_proxy_port }}` | {% if tls %}redirects to `websecure`{% if le %}; HTTP-01 challenge{% endif %}{% else %}default entry point of every router{% endif %} |
{%- if tls %}
| `websecure` | `:443`, host port `{{ cookiecutter.ifdd_proxy_tls_port }}` | default entry point of every router, TLS |
{%- endif %}
| `ping` | `127.0.0.1:8082` | health check only |

| Network | Members |
|---|---|
| `{{ cookiecutter.ifdd_proxy_network }}` (external) | Traefik{% if o2 %}, oauth2-proxy{% endif %} and every service behind the proxy |
{%- if sp %}
| `socket` (internal, of this project) | Traefik and the socket proxy |
{%- endif %}

## Mounts of the Traefik container

| Host | Container | |
|---|---|---|
{%- if not sp %}
| `/var/run/docker.sock` | `/var/run/docker.sock` | read-only flag, see {ref}`ifdd-proxy-security` |
{%- endif %}
| `traefik/traefik.yml` | `/etc/traefik/traefik.yml` | read-only |
| `traefik/dynamic/shared` | `/etc/traefik/dynamic/shared` | read-only |
{%- if tls %}
| `traefik/dynamic/production` | `/etc/traefik/dynamic/environment` | read-only |
{%- endif %}
| `traefik/private` | `/etc/traefik/dynamic/private` | read-only |
| `secrets` | `/etc/traefik/secrets` | read-only |
{%- if own %}
| `certs` | `/certs` | read-only |
{%- endif %}
{%- if le %}
| `letsencrypt` | `/letsencrypt` | read-write (`acme.json`) |
{%- endif %}
| `logs` | `/var/log/traefik` | read-write |

The development variant mounts `traefik/traefik.development.yml`{% if tls %},
`traefik/dynamic/development`{% endif %}, `traefik/dynamic/shared`, `secrets`
and `logs`.

## Middlewares (file provider)

| Name | Defined in | Attached |
|---|---|---|
| `dashboard-auth` | `dynamic/shared/dashboard.yml` | dashboard router |
{%- if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" %}
| `dos-baseline` (chain of `dos-ratelimit`, `dos-inflight`) | `dynamic/shared/dos.yml` | public entry point |
{%- if cookiecutter.ifdd_proxy_dos_enable_buffering == "y" %}
| `dos-buffering` | `dynamic/shared/dos.yml` | opt-in, per router |
{%- endif %}
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_security_headers == "y" %}
| `security-headers`, `csp-api`, `csp-api-docs`, `csp-ui` | `dynamic/shared/headers.yml` | per router, by the services |
{%- endif %}

Services reference them with the suffix `@file`, for example
`dashboard-auth@file`.

## Routers of this instance

| Router | Rule | Target |
|---|---|---|
| `dashboard` | `Host(<IFDD_PROXY_DASHBOARD_HOST>) && (PathPrefix(/api) \|\| PathPrefix(/dashboard))` | `api@internal`, with `dashboard-auth@file` |
{%- if o2 %}
| `oauth2-proxy` | `PathPrefix(/oauth2/)`, priority 1 | oauth2-proxy, port 4180 |
{%- endif %}
