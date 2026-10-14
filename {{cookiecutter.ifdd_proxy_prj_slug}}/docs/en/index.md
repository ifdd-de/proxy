(ifdd-proxy-index)=
# {{ cookiecutter.ifdd_proxy_prj_name }} (proxy)
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set sp = cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
{%- set o2 = cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

The reverse proxy in front of the IFDD services of a node. It is the only
service with published ports: it {% if tls %}terminates TLS, {% endif %}routes every host
name to its service, adds security headers and limits requests. This chapter
describes the instance `{{ cookiecutter.ifdd_proxy_prj_slug }}`, generated
from the template `ifdd-de/proxy`, from the point of view of the people who
set it up, run and secure it.

| | |
|---|---|
| Image | upstream `traefik:{{ cookiecutter.ifdd_proxy_traefik_version }}`, no image of its own |
| Shared network | `{{ cookiecutter.ifdd_proxy_network }}` (external, created once per host) |
| Host ports | `{{ cookiecutter.ifdd_proxy_port }}` (HTTP){% if tls %}, `{{ cookiecutter.ifdd_proxy_tls_port }}` (HTTPS){% endif %} |
| TLS | {% if tls %}on, minimum `{{ cookiecutter.ifdd_proxy_tls_min_version }}`, certificates {% if le %}from Let's Encrypt{% else %}from `certs/` (own certificates){% endif %}{% else %}off (plain HTTP){% endif %} |
| Dashboard | `{{ "https" if tls else "http" }}://{{ cookiecutter.ifdd_proxy_host }}/dashboard/` (default host; `IFDD_PROXY_DASHBOARD_HOST` in `.env`) |
| DoS baseline | {{ "on" if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" else "off" }} |
| Security headers | {{ "on" if cookiecutter.ifdd_proxy_enable_security_headers == "y" else "off" }} |
| Docker API | {{ "read-only through a socket proxy" if sp else "Docker socket mounted into the container" }} |
| Login gate (oauth2-proxy) | {{ "on" if o2 else "off" }} |

## What the instance contains

Configuration only: the static configuration of Traefik
(`traefik/traefik.yml`), dynamic configuration for the dashboard login, the
DoS baseline, the security headers and the TLS options, two compose files,
`.env` for the host ports and the dashboard host, and the generated secrets.
Services are not configured here: each one joins the network
`{{ cookiecutter.ifdd_proxy_network }}` and declares its router with Docker
labels, which Traefik reads from the Docker API.

## Architecture

```{mermaid}
flowchart LR
  Client[Browsers and clients] -->|"ports {{ cookiecutter.ifdd_proxy_port }}{% if tls %}, {{ cookiecutter.ifdd_proxy_tls_port }}{% endif %}"| Traefik[proxy: Traefik]
  Traefik -->|host name from labels| Services[services on {{ cookiecutter.ifdd_proxy_network }}]
  Services -->|public URLs, network aliases| Traefik
{%- if sp %}
  Traefik -->|read-only| SocketProxy[socket proxy] --> Docker[Docker API]
{%- else %}
  Traefik -->|socket| Docker[Docker API]
{%- endif %}
{%- if o2 %}
  Traefik -->|forwardAuth| OAuth2[oauth2-proxy]
  OAuth2 -->|OIDC| Traefik
{%- endif %}
```

Services call each other under their public URLs as well, for example the
backend fetching the signing keys of the realm. Inside the containers those
host names must lead to Traefik; the proxy container carries them as network
aliases (`ifdd_proxy_internal_hosts`, see {ref}`ifdd-proxy-setup`).

| Who | Uses the proxy for |
|---|---|
| every service with a browser or API host | routing, TLS, security headers, DoS limits |
| services that call other services (for example be, ct, wf) | the public URLs of Keycloak, the schema service and the backend, through the network aliases |
| services without a login of their own | the login gate oauth2-proxy (forwardAuth), if enabled |
| people | the dashboard (read-only view of routers, services, middlewares) |

## Chapters

```{toctree}
:maxdepth: 2

setup
build-release
operations
security
troubleshooting
reference
login-gate
```

The values of the variables of this instance and how they relate to the
other services are listed in the chapter on the service instances
({ref}`ifdd-instances-proxy`).
