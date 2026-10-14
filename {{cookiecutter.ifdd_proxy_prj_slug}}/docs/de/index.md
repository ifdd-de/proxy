(ifdd-proxy-index)=
# {{ cookiecutter.ifdd_proxy_prj_name }} (proxy)
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set sp = cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
{%- set o2 = cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

Der Reverse Proxy vor den IFDD-Diensten eines Knotens. Er ist der einzige
Dienst mit veröffentlichten Ports: Er {% if tls %}terminiert TLS, {% endif %}leitet jeden
Hostnamen an seinen Dienst, setzt Sicherheits-Header und begrenzt Anfragen.
Dieses Kapitel beschreibt die Instanz `{{ cookiecutter.ifdd_proxy_prj_slug }}`,
erzeugt aus dem Template `ifdd-de/proxy`, aus Sicht derer, die sie
einrichten, betreiben und absichern.

| | |
|---|---|
| Image | Upstream-Image `traefik:{{ cookiecutter.ifdd_proxy_traefik_version }}`, kein eigenes |
| Gemeinsames Netz | `{{ cookiecutter.ifdd_proxy_network }}` (extern, einmal je Host angelegt) |
| Host-Ports | `{{ cookiecutter.ifdd_proxy_port }}` (HTTP){% if tls %}, `{{ cookiecutter.ifdd_proxy_tls_port }}` (HTTPS){% endif %} |
| TLS | {% if tls %}an, mindestens `{{ cookiecutter.ifdd_proxy_tls_min_version }}`, Zertifikate {% if le %}von Let's Encrypt{% else %}aus `certs/` (eigene Zertifikate){% endif %}{% else %}aus (reines HTTP){% endif %} |
| Dashboard | `{{ "https" if tls else "http" }}://{{ cookiecutter.ifdd_proxy_host }}/dashboard/` (Standard-Host; `IFDD_PROXY_DASHBOARD_HOST` in `.env`) |
| DoS-Grundschutz | {{ "an" if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" else "aus" }} |
| Sicherheits-Header | {{ "an" if cookiecutter.ifdd_proxy_enable_security_headers == "y" else "aus" }} |
| Docker-API | {{ "nur lesend über einen Socket-Proxy" if sp else "Docker-Socket in den Container eingebunden" }} |
| Login-Gate (oauth2-proxy) | {{ "an" if o2 else "aus" }} |

## Was die Instanz enthält

Nur Konfiguration: die statische Konfiguration von Traefik
(`traefik/traefik.yml`), dynamische Konfiguration für die Dashboard-Anmeldung,
den DoS-Grundschutz, die Sicherheits-Header und die TLS-Optionen, zwei
Compose-Dateien, `.env` für die Host-Ports und den Dashboard-Host sowie die
erzeugten Secrets. Dienste werden hier nicht konfiguriert: Jeder tritt dem
Netz `{{ cookiecutter.ifdd_proxy_network }}` bei und erklärt seinen Router
mit Docker-Labels, die Traefik über die Docker-API liest.

## Architektur

```{mermaid}
flowchart LR
  Client[Browser und Clients] -->|"Ports {{ cookiecutter.ifdd_proxy_port }}{% if tls %}, {{ cookiecutter.ifdd_proxy_tls_port }}{% endif %}"| Traefik[proxy: Traefik]
  Traefik -->|Hostname aus Labels| Services[Dienste in {{ cookiecutter.ifdd_proxy_network }}]
  Services -->|öffentliche URLs, Netz-Aliasse| Traefik
{%- if sp %}
  Traefik -->|nur lesend| SocketProxy[Socket-Proxy] --> Docker[Docker-API]
{%- else %}
  Traefik -->|Socket| Docker[Docker-API]
{%- endif %}
{%- if o2 %}
  Traefik -->|forwardAuth| OAuth2[oauth2-proxy]
  OAuth2 -->|OIDC| Traefik
{%- endif %}
```

Auch untereinander rufen sich Dienste unter ihren öffentlichen URLs auf, etwa
das Backend, wenn es die Signaturschlüssel des Realms holt. In den Containern
müssen diese Hostnamen zu Traefik führen; der Proxy-Container trägt sie als
Netz-Aliasse (`ifdd_proxy_internal_hosts`, siehe {ref}`ifdd-proxy-setup`).

| Wer | Nutzt den Proxy für |
|---|---|
| jeder Dienst mit einem Browser- oder API-Host | Routing, TLS, Sicherheits-Header, DoS-Grenzen |
| Dienste, die andere Dienste aufrufen (etwa be, ct, wf) | die öffentlichen URLs von Keycloak, Schema-Dienst und Backend, über die Netz-Aliasse |
| Dienste ohne eigene Anmeldung | das Login-Gate oauth2-proxy (forwardAuth), wenn eingeschaltet |
| Menschen | das Dashboard (nur lesende Sicht auf Router, Dienste, Middlewares) |

## Kapitel

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

Die Werte der Variablen dieser Instanz und ihre Beziehungen zu den anderen
Diensten stehen im Kapitel über die Dienst-Instanzen
({ref}`ifdd-instances-proxy`).
