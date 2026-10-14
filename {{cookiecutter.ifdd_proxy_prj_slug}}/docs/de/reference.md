(ifdd-proxy-reference)=
# Referenz
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set own = tls and not le %}
{%- set sp = cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
{%- set o2 = cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

Die Variablen des Templates und ihre Werte in dieser Instanz stehen in
{ref}`ifdd-instances-proxy`. Diese Seite führt auf, was keine
Template-Variable ist.

## Aufbau

| Pfad | Zweck |
|---|---|
| `traefik/traefik.yml` | statische Konfiguration, Produktion (die einzige Quelle: keine CLI-Flags, keine `TRAEFIK_*`-Variablen) |
| `traefik/traefik.development.yml` | statische Konfiguration, lokale Entwicklung |
| `traefik/dynamic/shared/` | Dashboard-Anmeldung{% if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" %}, DoS-Grundschutz{% endif %}{% if cookiecutter.ifdd_proxy_enable_security_headers == "y" %}, Sicherheits-Header{% endif %} |
{%- if tls %}
| `traefik/dynamic/production/`, `traefik/dynamic/development/` | TLS-Optionen je Umgebung |
{%- endif %}
| `traefik/private/` | instanzeigene dynamische Konfiguration (weitere Zertifikate, Router); jede `*.yml` wird in Produktion geladen |
| `secrets/` | `dashboard.htpasswd`{% if o2 %}, `oauth2_proxy_cookie_secret`, `oauth2_proxy_client_secret`{% endif %}; von Git ausgenommen |
{%- if own %}
| `certs/` | eigene Zertifikate und Schlüssel, von Git ausgenommen |
| `adm_01_certs.sh` | lokale CA und Standardzertifikat, einmalig |
{%- endif %}
{%- if le %}
| `letsencrypt/` | ACME-Konto und Zertifikate (`acme.json`), von Git ausgenommen |
{%- endif %}
| `logs/` | Access-Log |
| `dotenv.dist` → `.env` | Werte für die Compose-Dateien |
| `tests/` | statische Prüfungen und Smoke-Test |

## Umgebung (`.env`)

Nur von Docker Compose für die `${...}` der Compose-Dateien gelesen; an keinen
Container weitergereicht, außer wo vermerkt.

| Variable | Vorgabe hier | Bedeutung |
|---|---|---|
| `IFDD_PROXY_DASHBOARD_HOST` | `{{ cookiecutter.ifdd_proxy_host }}` | Host des Dashboard-Routers (Pfade `/dashboard`, `/api`) |
| `IFDD_PROXY_DASHBOARD_USER` | `{{ cookiecutter.ifdd_proxy_dashboard_user }}` | nur zum Nachlesen; Traefik prüft `secrets/dashboard.htpasswd` |
| `IFDD_PROXY_DASHBOARD_PASSWORD` | erzeugt | nur zum Nachlesen |
| `IFDD_PROXY_HTTP_PORT` | `{{ cookiecutter.ifdd_proxy_port }}` | Host-Port für HTTP |
| `IFDD_PROXY_HTTPS_PORT` | `{{ cookiecutter.ifdd_proxy_tls_port }}` | Host-Port für HTTPS{% if not tls %} (ungenutzt: TLS ist aus){% endif %} |
{%- if o2 %}
| `IFDD_PROXY_OIDC_ISSUER` | `{{ cookiecutter.ifdd_proxy_oidc_issuer }}` | Realm-URL; an oauth2-proxy weitergereicht |
| `IFDD_PROXY_OIDC_CLIENT_ID` | `{{ cookiecutter.ifdd_proxy_oidc_client_id }}` | Client von oauth2-proxy; an oauth2-proxy weitergereicht |
{%- endif %}

## Entry Points, Ports und Netze

| Entry Point | Adresse | Zweck |
|---|---|---|
| `web` | `:80`, Host-Port `{{ cookiecutter.ifdd_proxy_port }}` | {% if tls %}leitet auf `websecure` um{% if le %}; HTTP-01-Challenge{% endif %}{% else %}Standard-Entry-Point jedes Routers{% endif %} |
{%- if tls %}
| `websecure` | `:443`, Host-Port `{{ cookiecutter.ifdd_proxy_tls_port }}` | Standard-Entry-Point jedes Routers, TLS |
{%- endif %}
| `ping` | `127.0.0.1:8082` | nur Healthcheck |

| Netz | Mitglieder |
|---|---|
| `{{ cookiecutter.ifdd_proxy_network }}` (extern) | Traefik{% if o2 %}, oauth2-proxy{% endif %} und jeder Dienst hinter dem Proxy |
{%- if sp %}
| `socket` (intern, aus diesem Projekt) | Traefik und der Socket-Proxy |
{%- endif %}

## Mounts des Traefik-Containers

| Host | Container | |
|---|---|---|
{%- if not sp %}
| `/var/run/docker.sock` | `/var/run/docker.sock` | Flag „nur lesend“, siehe {ref}`ifdd-proxy-security` |
{%- endif %}
| `traefik/traefik.yml` | `/etc/traefik/traefik.yml` | nur lesend |
| `traefik/dynamic/shared` | `/etc/traefik/dynamic/shared` | nur lesend |
{%- if tls %}
| `traefik/dynamic/production` | `/etc/traefik/dynamic/environment` | nur lesend |
{%- endif %}
| `traefik/private` | `/etc/traefik/dynamic/private` | nur lesend |
| `secrets` | `/etc/traefik/secrets` | nur lesend |
{%- if own %}
| `certs` | `/certs` | nur lesend |
{%- endif %}
{%- if le %}
| `letsencrypt` | `/letsencrypt` | lesend und schreibend (`acme.json`) |
{%- endif %}
| `logs` | `/var/log/traefik` | lesend und schreibend |

Die Entwicklungsvariante bindet `traefik/traefik.development.yml`{% if tls %},
`traefik/dynamic/development`{% endif %}, `traefik/dynamic/shared`, `secrets`
und `logs` ein.

## Middlewares (File-Provider)

| Name | Definiert in | Angehängt |
|---|---|---|
| `dashboard-auth` | `dynamic/shared/dashboard.yml` | Dashboard-Router |
{%- if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" %}
| `dos-baseline` (Kette aus `dos-ratelimit`, `dos-inflight`) | `dynamic/shared/dos.yml` | öffentlicher Entry Point |
{%- if cookiecutter.ifdd_proxy_dos_enable_buffering == "y" %}
| `dos-buffering` | `dynamic/shared/dos.yml` | auf Wunsch, je Router |
{%- endif %}
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_security_headers == "y" %}
| `security-headers`, `csp-api`, `csp-api-docs`, `csp-ui` | `dynamic/shared/headers.yml` | je Router, durch die Dienste |
{%- endif %}

Dienste verweisen mit dem Suffix `@file` auf sie, zum Beispiel
`dashboard-auth@file`.

## Router dieser Instanz

| Router | Regel | Ziel |
|---|---|---|
| `dashboard` | `Host(<IFDD_PROXY_DASHBOARD_HOST>) && (PathPrefix(/api) \|\| PathPrefix(/dashboard))` | `api@internal`, mit `dashboard-auth@file` |
{%- if o2 %}
| `oauth2-proxy` | `PathPrefix(/oauth2/)`, Priorität 1 | oauth2-proxy, Port 4180 |
{%- endif %}
