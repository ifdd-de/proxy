(ifdd-proxy-setup)=
# Setup
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set own = tls and not le %}
{%- set internal_hosts = cookiecutter.ifdd_proxy_internal_hosts.split(",") | map("trim") | reject("equalto", "") | list %}

## Prerequisites

| What | Why |
|---|---|
| Docker with Compose | Traefik{% if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}, the socket proxy{% endif %}{% if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %} and oauth2-proxy{% endif %} run as containers |
| free host ports `{{ cookiecutter.ifdd_proxy_port }}`{% if tls %} and `{{ cookiecutter.ifdd_proxy_tls_port }}`{% endif %} | the only published ports of the node |
| every host name of every service resolves to this machine for its users | DNS or `/etc/hosts` of the clients; inside the containers the network aliases take over (see below) |
{%- if own %}
| certificates and keys for those host names, or `openssl` for `adm_01_certs.sh` | own certificates (`certs/`) |
{%- elif le %}
| port 80 of this machine reachable from the internet, a valid e-mail address in `ifdd_proxy_letsencrypt_email` | the HTTP-01 challenge of Let's Encrypt |
{%- endif %}

## Create the instance

Usually the meta repository creates every instance in one go
(`.adm_meta_01_all.sh`, step `.adm_01_create_services.sh`): it runs
`cruft create` with the shared variable file `.cookiecutter_all.yaml`, runs
`adm_01_certs.sh` here and copies `certs/ca.crt` into the services that need
it, and copies the client secret of oauth2-proxy from the Keycloak instance.

By hand, from the directory that holds the instances, with the skip list
this template recommends:

```bash
cruft create --no-input --config-file .cookiecutter_all.yaml \
  --skip .env --skip secrets --skip certs --skip letsencrypt \
  --skip logs --skip traefik/private \
  https://github.com/ifdd-de/proxy
```

The skip list keeps the files that belong to the instance (environment,
secrets, keys, ACME state, private dynamic configuration) out of every later
`cruft update`. The meta repository passes `--skip envs --skip .env --skip
secrets`.

## Configuration and secrets

The post-generation hook

- writes `.env` from `dotenv.dist` (mode 0600);
- generates a dashboard password (32 letters and digits) for the user
  `{{ cookiecutter.ifdd_proxy_dashboard_user }}`, writes it into `.env`
  (`IFDD_PROXY_DASHBOARD_PASSWORD`, for reading only) and the matching APR1
  line into `secrets/dashboard.htpasswd`;
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}
- generates the cookie secret of oauth2-proxy
  (`secrets/oauth2_proxy_cookie_secret`) and creates an empty
  `secrets/oauth2_proxy_client_secret` for the client secret from Keycloak;
{%- endif %}
- removes the files the chosen options do not use.

An existing `secrets/dashboard.htpasswd` is kept. `.env` only feeds the
`${...}` of the compose files and never reaches the containers: Traefik reads
every `TRAEFIK_*` variable in its environment as configuration. Keep the
prefix `IFDD_PROXY_` for anything added there. The entries are listed in
{ref}`ifdd-proxy-reference`.

Every other value comes from the variables of the template; they are listed
with their values and meaning in {ref}`ifdd-instances-proxy`.

## Internal host names

Services call each other under their public URLs: the backend fetches the
signing keys of Keycloak from `https://<keycloak host>/...` and JSON-LD
contexts from `https://<schema host>/...`. Inside a container those names
must lead to this proxy. Docker does not hand the host's `/etc/hosts` to the
containers, and a host that maps the names to `127.0.0.1` would send each
container to itself.

`ifdd_proxy_internal_hosts` lists the names that containers on
`{{ cookiecutter.ifdd_proxy_network }}` resolve to this proxy (network
aliases of the proxy container). This instance:
{% if internal_hosts %}{% for host in internal_hosts %}`{{ host }}`{{ ", " if not loop.last else "." }}{% endfor %}{% else %}none.{% endif %}
List every host name that one service calls on another, and only names this
proxy routes: an alias shadows any other resolution of that name for all
containers on the network.

The calling service must also trust the proxy's certificate: its image takes
the CA certificate from its own `certs/` directory at build time (see the
documentation of that service).

Check from inside a service container that a name leads to the proxy:

```bash
docker compose exec <service> getent hosts <host>
docker network inspect {{ cookiecutter.ifdd_proxy_network }} --format {% raw %}'{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'{% endraw %}
```

The address of the first command must be the proxy's.

## Certificates
{%- if own %}

Put the default certificate and its key into `certs/` as
`{{ cookiecutter.ifdd_proxy_default_cert_file }}` and
`{{ cookiecutter.ifdd_proxy_default_key_file }}`. Further certificates go
into `traefik/private/certificates.yml` (copy `certificates.yml.dist` there).
Clients that send no server name, or one no certificate covers, are refused
(`sniStrict`).

Without certificates of your own, `./adm_01_certs.sh` creates, once, a local
CA (`certs/ca.crt`, `certs/ca.key`) and the default certificate signed by it.
The certificate covers the internal host names above and
`IFDD_PROXY_DASHBOARD_HOST` from `.env`. The script refuses to run when any
of the four files exists, so certificates of your own are never touched; to
start over, delete all four.

1. Run it before the first start: `./adm_01_certs.sh`.
2. Trust `certs/ca.crt` in the browser or the operating system of everyone
   who uses the services.
3. Copy `certs/ca.crt` into `certs/` of every service that calls another one
   through this proxy, and rebuild its image.
{%- elif le %}

Traefik requests the certificates from Let's Encrypt
({{ "staging CA" if cookiecutter.ifdd_proxy_letsencrypt_staging == "y" else "production CA" }})
with the HTTP-01 challenge and stores them in `letsencrypt/acme.json`; the
resolver is set on the entry point `websecure`, so every router gets it.
Make sure that every host name of every router resolves to this machine and
that port 80 is reachable from the internet. Until the first certificate is
issued, HTTPS handshakes fail (`sniStrict` refuses Traefik's self-signed
fallback certificate). Test against the staging CA first
(`ifdd_proxy_letsencrypt_staging`): the production CA rate-limits failed
attempts.
{%- else %}

TLS is off in this instance: Traefik serves plain HTTP on port
`{{ cookiecutter.ifdd_proxy_port }}` and needs no certificates. Services that
call each other over HTTPS cannot work with it.
{%- endif %}

## First start

```bash
docker network create {{ cookiecutter.ifdd_proxy_network }}   # once per host, if it does not exist yet
docker compose -f docker-compose-production.yml up -d
docker compose -f docker-compose-production.yml ps
```

The network is external to every compose project, the proxy included, so no
`down` removes it while other services are still attached. `ps` should report
the proxy as healthy. The dashboard is at
`{{ "https" if tls else "http" }}://<dashboard host>/dashboard/`, with the
trailing slash; the login is `IFDD_PROXY_DASHBOARD_USER` with
`IFDD_PROXY_DASHBOARD_PASSWORD` from `.env`.
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}
With the login gate, start Traefik alone first; see
{ref}`ifdd-proxy-operations`.
{%- endif %}

## Local development

```bash
docker compose -f docker-compose-development.yml up -d
```

Traefik serves its self-signed default certificate, so browsers warn, and
`sniStrict` is off for that reason. `secrets/dashboard.htpasswd` is needed
for the dashboard as in production. No client can verify that certificate,
so services that call each other over HTTPS through the proxy (token
validation, JSON-LD contexts) fail in development; use the production
variant for that. The development variant mounts neither `certs/` nor
`traefik/private/` and never uses Let's Encrypt.

## Wiring a service

A service joins the network and declares its router with labels:

```yaml
services:
  api:
    networks: [ext-proxy-net]
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`api.example.org`)"
      - "traefik.http.services.api.loadbalancer.server.port=8881"
      - "traefik.docker.network={{ cookiecutter.ifdd_proxy_network }}"
{%- if cookiecutter.ifdd_proxy_enable_security_headers == "y" %}
      - "traefik.http.routers.api.middlewares=security-headers@file,csp-api@file"
{%- endif %}

networks:
  ext-proxy-net:
    name: {{ cookiecutter.ifdd_proxy_network }}
    external: true
```

`api` and `api.example.org` are examples. Containers without
`traefik.enable=true` are ignored (`exposedByDefault: false`).

- **No router `tls` labels.** TLS{% if le %} and the certificate resolver{% endif %}
  are set on the entry point. A router that declares any `tls` section of its
  own, even just `...routers.api.tls=true`, replaces that configuration
  completely. Checked against Traefik v3.7.13: such a router ends up with no
  TLS configuration at all.
- **No `entrypoints` label needed.** Routers without one attach to the
  default entry point (`websecure`, or `web` without TLS).
{%- if cookiecutter.ifdd_proxy_enable_security_headers == "y" %}
- **Security headers** are attached per router; which CSP fits which kind of
  host is described in {ref}`ifdd-proxy-security`.
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" and cookiecutter.ifdd_proxy_dos_enable_buffering == "y" %}
- **Request body limit, opt-in:** add `dos-buffering@file` to the router's
  middlewares. It is not part of the global DoS baseline: attached to the
  entry point it also wraps the dashboard, and with v3.7.13 every dashboard
  request then fails. Buffering holds the whole request before forwarding
  it, which does not suit streaming uploads.
{%- endif %}
