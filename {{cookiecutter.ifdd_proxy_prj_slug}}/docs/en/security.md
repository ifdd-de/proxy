(ifdd-proxy-security)=
# Security
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set own = tls and not le %}
{%- set sp = cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
{%- set headers = cookiecutter.ifdd_proxy_enable_security_headers == "y" %}
{%- set trusted = cookiecutter.ifdd_proxy_trusted_ips.split(",") | map("trim") | select | list %}

The proxy is the only service reachable from outside the host. What it
protects, and what it does not:

| Concern | Here |
|---|---|
| transport encryption | {% if tls %}TLS on every router, minimum `{{ cookiecutter.ifdd_proxy_tls_min_version }}`, HTTP redirects to HTTPS{% else %}none: plain HTTP{% endif %} |
| who may use a service | the service itself (access tokens), or the login gate in front of it ({ref}`ifdd-proxy-login-gate`) |
| browser hardening | {% if headers %}security headers and a CSP per kind of host, attached by each service{% else %}off (`ifdd_proxy_enable_security_headers`){% endif %} |
| request floods | {{ "DoS baseline on the public entry point" if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" else "no DoS baseline" }} ({ref}`ifdd-proxy-operations`) |
| access to Docker | {{ "read-only through the socket proxy" if sp else "the Docker socket, mounted into the container" }} |

## TLS
{%- if tls %}

- TLS is configured on the entry point `websecure`; routers inherit it.
  **Services must not set router `tls` labels**: a router with a `tls`
  section of its own replaces the configuration of the entry point
  completely{% if le %}, including the Let's Encrypt resolver{% endif %}
  (checked against Traefik v3.7.13).
- Minimum version `{{ cookiecutter.ifdd_proxy_tls_min_version }}`
  (`ifdd_proxy_tls_min_version`).
- `sniStrict` in production: clients that send no server name, or one no
  certificate covers, are refused instead of getting the default
  certificate.
- `strictTLSOptions`: two routers asking for different TLS options on the
  same host name fail instead of silently falling back to the default
  options.
{%- if own %}
- `certs/ca.key` from `adm_01_certs.sh` can issue certificates for any name
  that clients trusting the CA accept. Keep it on this host only; it is
  git-ignored and mounted into no container except Traefik's `certs/` mount.
{%- if cookiecutter.ifdd_proxy_oauth2_proxy_ca_file %}
  oauth2-proxy gets only `certs/{{ cookiecutter.ifdd_proxy_oauth2_proxy_ca_file }}`, never the directory.
{%- endif %}
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_hsts == "y" %}
- HSTS is on (`max-age` {{ cookiecutter.ifdd_proxy_hsts_seconds }} s, with
  subdomains). Browsers that saw it refuse plain HTTP to these hosts until it
  expires.
{%- else %}
- HSTS is off. Turn it on (`ifdd_proxy_enable_hsts`) only when every host is
  HTTPS-only: it sticks in the browser.
{%- endif %}
{%- else %}

TLS is off in this instance. Tokens, passwords and the dashboard login
travel in plain text; use it only on a trusted network.
{%- endif %}

## Dashboard

- Served only through the router `dashboard` on `IFDD_PROXY_DASHBOARD_HOST`,
  with basic authentication (`dashboard-auth`, users in
  `secrets/dashboard.htpasswd`); `api.insecure` is off, so there is no
  unauthenticated port 8080. The credentials are not forwarded to the
  dashboard service (`removeHeader`).
- The generated hash is APR1-MD5, the strongest format Traefik accepts that
  the Python standard library can compute. Prefer bcrypt for a password you
  set yourself: `htpasswd -nB <user> > secrets/dashboard.htpasswd`, then
  restart the proxy and update `.env` to match.
- Basic authentication checks the password on every request; a high bcrypt
  cost slows down every dashboard request.
- The dashboard shows the routers, services and middlewares of the node,
  including host names and internal addresses. Give the login only to
  operators.

## Configuration sources

Traefik takes its static configuration from exactly one source,
`traefik/traefik.yml`. The compose files pass only `--configFile` and no
`env_file`: Traefik reads every `TRAEFIK_*` variable in its environment as
configuration, so nothing from `.env` reaches the container. The instance
tests check both.

## Docker API
{%- if sp %}

Traefik reads the Docker API through the socket proxy
(`tcp://socket-proxy:2375`) on an internal network that only the two
containers share. The socket proxy grants listing and inspecting containers
(`CONTAINERS=1`) plus its defaults (events, ping, version); every write
request is refused.

```{note}
Not verified: the tag format of the socket proxy image. With SELinux the
socket proxy may need `privileged: true`.
```
{%- else %}

The Docker socket is mounted into the Traefik container with `:ro`. That is
read-only in name only: the Docker API behind the socket still accepts write
requests, and whoever controls the container controls the host.
`ifdd_proxy_enable_socket_proxy=y` replaces the mount with a read-only socket
proxy.
{%- endif %}

Containers are not exposed by default (`exposedByDefault: false`): only
services with `traefik.enable=true` get a router.

## Security headers
{%- if headers %}

`traefik/dynamic/shared/headers.yml` defines response-header middlewares.
They are **not** attached here; each service references them in its own
router label, so the CSP fits the host:

```text
traefik.http.routers.<name>.middlewares=security-headers@file,<csp>@file
```

| Middleware | Content | For |
|---|---|---|
| `security-headers` | `X-Content-Type-Options: nosniff`, `X-Frame-Options: {{ cookiecutter.ifdd_proxy_frame_options }}`, `Referrer-Policy: {{ cookiecutter.ifdd_proxy_referrer_policy }}`, removes the upstream `Server` header{% if cookiecutter.ifdd_proxy_enable_hsts == "y" %}, HSTS{% endif %} | every service |
| `csp-api` | `{{ cookiecutter.ifdd_proxy_csp_api }}` | JSON APIs without a browser UI (schema, type, unit) |
| `csp-api-docs` | `{{ cookiecutter.ifdd_proxy_csp_api_docs }}` | the backend, which also serves Swagger UI and ReDoc (`/docs`, `/redoc`) |
| `csp-ui` | `{{ cookiecutter.ifdd_proxy_csp_ui }}` | the react-admin frontend |

A service picks one `csp-*` next to `security-headers`, or none. Keycloak
uses `security-headers` only and keeps the CSP it sets itself; its admin
console and login pages would break under `csp-api`.

- `csp-api-docs` must name the origin of the realm in `connect-src`, because
  "Authorize" in Swagger UI fetches the token there; `worker-src 'self'
  blob:` and `style-src 'unsafe-inline'` are for ReDoc. The template default
  has no realm origin; the value comes from `.cookiecutter_all.yaml`.
- `csp-ui` must list the origins the frontend talks to cross-origin in
  `connect-src`: the OIDC provider (token, userinfo), the backend, and the
  type and unit services (the UI reads labels, help texts and units from
  their vocabularies); and the OIDC auth endpoint in `frame-src` for silent
  token renewal. Keep these in step with `ifdd_oidc_realm`, `ifdd_be_url`,
  `ifdd_type_url` and `ifdd_unit_url`.

Verify the UI and the Keycloak console in the browser console after a change
and tighten the policies as far as they still work.
{%- else %}

Off in this instance (`ifdd_proxy_enable_security_headers`): there is no
`headers.yml`, and services must not reference `security-headers@file` or a
`csp-*@file` middleware; a router that names a missing middleware is not
served.
{%- endif %}

## Client addresses and forwarded headers

{% if trusted -%}
Traefik trusts `X-Forwarded-*` from {% for ip in trusted %}`{{ ip }}`{{ ", " if not loop.last else "" }}{% endfor %}
(`ifdd_proxy_trusted_ips`) and removes it from every other source.
{%- else -%}
No proxy in front is trusted (`ifdd_proxy_trusted_ips` is empty): Traefik
removes `X-Forwarded-*` from incoming requests and sets its own.
{%- endif %}

Request headers that contain `_` instead of `-` (such as
`X_Auth_User`), which some servers treat like their `-` spelling, are
handled with the strategy `{{ cookiecutter.ifdd_proxy_alias_headers_strategy }}`
(`ifdd_proxy_alias_headers_strategy`) on every entry point.

## Containers

All containers run with `no-new-privileges`. Secrets are in `.env` (mode
0600) and `secrets/` (mode 0700), both git-ignored and on the skip list;
`secrets/` is mounted read-only, `.env` not at all.
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}
oauth2-proxy runs with a read-only root file system and has no published
port; its trust in `X-Forwarded-*` is described in
{ref}`ifdd-proxy-login-gate`.
{%- endif %}
