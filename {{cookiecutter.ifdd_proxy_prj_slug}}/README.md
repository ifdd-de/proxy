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
{%- if tls %}
./adm_check_hosts.sh                  # how the host names of this server reach their services
{%- endif %}
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

## AI assistance

Some parts of the template `ifdd-de/proxy` this instance was generated
from, in particular the tests, the test data and the documentation, were
developed or improved with the help of large language models (LLMs). All
changes were reviewed and released by the maintainer.

## License

BSD-3-Clause, see `LICENSE`.
