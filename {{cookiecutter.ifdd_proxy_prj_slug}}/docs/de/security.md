(ifdd-proxy-security)=
# Sicherheit
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set own = tls and not le %}
{%- set sp = cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
{%- set headers = cookiecutter.ifdd_proxy_enable_security_headers == "y" %}
{%- set trusted = cookiecutter.ifdd_proxy_trusted_ips.split(",") | map("trim") | select | list %}

Der Proxy ist der einzige Dienst, der von außerhalb des Hosts erreichbar ist.
Was er schützt und was nicht:

| Thema | Hier |
|---|---|
| Transportverschlüsselung | {% if tls %}TLS an jedem Router, mindestens `{{ cookiecutter.ifdd_proxy_tls_min_version }}`, HTTP leitet auf HTTPS um{% else %}keine: reines HTTP{% endif %} |
| wer einen Dienst nutzen darf | der Dienst selbst (Access-Tokens) oder das Login-Gate vor ihm ({ref}`ifdd-proxy-login-gate`) |
| Härtung im Browser | {% if headers %}Sicherheits-Header und eine CSP je Art Host, angehängt von jedem Dienst{% else %}aus (`ifdd_proxy_enable_security_headers`){% endif %} |
| Anfragefluten | {{ "DoS-Grundschutz am öffentlichen Entry Point" if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" else "kein DoS-Grundschutz" }} ({ref}`ifdd-proxy-operations`) |
| Zugriff auf Docker | {{ "nur lesend über den Socket-Proxy" if sp else "der Docker-Socket, in den Container eingebunden" }} |

## TLS
{%- if tls %}

- TLS ist am Entry Point `websecure` konfiguriert; Router erben es.
  **Dienste dürfen keine `tls`-Labels am Router setzen**: Ein Router mit
  eigenem `tls`-Abschnitt ersetzt die Konfiguration des Entry Points
  vollständig{% if le %}, einschließlich des Let's-Encrypt-Resolvers{% endif %}
  (geprüft mit Traefik v3.7.13).
- Mindestversion `{{ cookiecutter.ifdd_proxy_tls_min_version }}`
  (`ifdd_proxy_tls_min_version`).
- `sniStrict` in Produktion: Clients, die keinen Servernamen senden oder einen,
  den kein Zertifikat abdeckt, werden abgewiesen, statt das
  Standardzertifikat zu bekommen.
- `strictTLSOptions`: Zwei Router, die für denselben Hostnamen verschiedene
  TLS-Optionen verlangen, scheitern, statt still auf die Standardoptionen
  zurückzufallen.
{%- if own %}
- `certs/ca.key` aus `adm_01_certs.sh` kann Zertifikate für jeden Namen
  ausstellen, den Clients mit Vertrauen in die CA annehmen. Nur auf diesem
  Host aufbewahren; die Datei ist von Git ausgenommen und in keinen Container
  eingebunden außer über den `certs/`-Mount von Traefik.
{%- if cookiecutter.ifdd_proxy_oauth2_proxy_ca_file %}
  oauth2-proxy bekommt nur `certs/{{ cookiecutter.ifdd_proxy_oauth2_proxy_ca_file }}`, nie das Verzeichnis.
{%- endif %}
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_hsts == "y" %}
- HSTS ist an (`max-age` {{ cookiecutter.ifdd_proxy_hsts_seconds }} s, mit
  Subdomains). Browser, die es gesehen haben, verweigern reines HTTP zu diesen
  Hosts, bis es abläuft.
{%- else %}
- HSTS ist aus. Nur einschalten (`ifdd_proxy_enable_hsts`), wenn jeder Host
  ausschließlich HTTPS spricht: Es bleibt im Browser hängen.
{%- endif %}
{%- else %}

TLS ist in dieser Instanz aus. Tokens, Passwörter und die Dashboard-Anmeldung
gehen im Klartext über das Netz; nur in einem vertrauenswürdigen Netz nutzen.
{%- endif %}

## Dashboard

- Nur über den Router `{{ cookiecutter.ifdd_proxy_prj_slug }}-dashboard` auf `IFDD_PROXY_DASHBOARD_HOST` ausgeliefert,
  mit Basic Authentication (`dashboard-auth`, Benutzer in
  `secrets/dashboard.htpasswd`); `api.insecure` ist aus, es gibt also keinen
  Port 8080 ohne Anmeldung. Die Anmeldedaten werden nicht an den
  Dashboard-Dienst weitergereicht (`removeHeader`).
- Der erzeugte Hash ist APR1-MD5, das stärkste Format, das Traefik annimmt und
  die Python-Standardbibliothek berechnen kann. Für ein selbst gesetztes
  Passwort besser bcrypt: `htpasswd -nB <user> > secrets/dashboard.htpasswd`,
  dann den Proxy neu starten und `.env` anpassen.
- Basic Authentication prüft das Passwort bei jeder Anfrage; hohe
  bcrypt-Kosten verlangsamen jede Dashboard-Anfrage.
- Das Dashboard zeigt Router, Dienste und Middlewares des Knotens, samt
  Hostnamen und internen Adressen. Die Anmeldung nur an Betreiber geben.

## Quellen der Konfiguration

Traefik nimmt seine statische Konfiguration aus genau einer Quelle,
`traefik/traefik.yml`. Die Compose-Dateien übergeben nur `--configFile` und
kein `env_file`: Traefik liest jede `TRAEFIK_*`-Variable seiner Umgebung als
Konfiguration, also erreicht nichts aus `.env` den Container. Die Tests der
Instanz prüfen beides.

## Docker-API
{%- if sp %}

Traefik liest die Docker-API über den Socket-Proxy (`tcp://socket-proxy:2375`)
in einem internen Netz, das nur diese beiden Container teilen. Der
Socket-Proxy erlaubt Auflisten und Untersuchen von Containern
(`CONTAINERS=1`) plus seine Vorgaben (Events, Ping, Version); jede schreibende
Anfrage weist er ab.

```{note}
Nicht geprüft: das Tag-Format des Socket-Proxy-Images. Mit SELinux braucht der
Socket-Proxy womöglich `privileged: true`.
```
{%- else %}

Der Docker-Socket ist mit `:ro` in den Traefik-Container eingebunden. Das ist
nur dem Namen nach schreibgeschützt: Die Docker-API hinter dem Socket nimmt
weiterhin schreibende Anfragen an, und wer den Container beherrscht,
beherrscht den Host. `ifdd_proxy_enable_socket_proxy=y` ersetzt den Mount
durch einen nur lesenden Socket-Proxy.
{%- endif %}

Container sind nicht von sich aus erreichbar (`exposedByDefault: false`): Nur
Dienste mit `traefik.enable=true` bekommen einen Router.

Router-, Dienst- und Middleware-Namen kommen aus den Projekt-Slugs der
Instanzen (hier `{{ cookiecutter.ifdd_proxy_prj_slug }}-dashboard`, `{{ cookiecutter.ifdd_proxy_prj_slug }}-oauth2-proxy`), damit die Namen
zweier Instanzen nicht kollidieren. Der Docker-Provider hat aber keine
Constraints: Ein zweiter Proxy auf demselben Docker-Host sähe auch die
Container und Labels dieses Proxys, einschließlich seines Dashboard-Routers,
und umgekehrt. Zwei Proxies auf einem Host brauchen zuerst Constraints für
den Provider.

```{note}
Nicht geprüft: zwei Proxies auf einem Docker-Host.
```

## Sicherheits-Header
{%- if headers %}

`traefik/dynamic/shared/headers.yml` definiert Middlewares für
Antwort-Header. Sie werden hier **nicht** angehängt; jeder Dienst verweist in
seinem eigenen Router-Label auf sie, damit die CSP zum Host passt:

```text
traefik.http.routers.<name>.middlewares=security-headers@file,<csp>@file
```

| Middleware | Inhalt | Für |
|---|---|---|
| `security-headers` | `X-Content-Type-Options: nosniff`, `X-Frame-Options: {{ cookiecutter.ifdd_proxy_frame_options }}`, `Referrer-Policy: {{ cookiecutter.ifdd_proxy_referrer_policy }}`, entfernt den `Server`-Header des Dienstes{% if cookiecutter.ifdd_proxy_enable_hsts == "y" %}, HSTS{% endif %} | jeden Dienst |
| `csp-api` | `{{ cookiecutter.ifdd_proxy_csp_api }}` | JSON-APIs ohne Browser-Oberfläche (schema, type, unit) |
| `csp-api-docs` | `{{ cookiecutter.ifdd_proxy_csp_api_docs }}` | das Backend, das auch Swagger UI und ReDoc ausliefert (`/docs`, `/redoc`) |
| `csp-ui` | `{{ cookiecutter.ifdd_proxy_csp_ui }}` | das react-admin-Frontend |

Ein Dienst wählt eine `csp-*` neben `security-headers` oder keine. Keycloak
nutzt nur `security-headers` und behält die CSP, die es selbst setzt; seine
Admin-Konsole und Anmeldeseiten würden unter `csp-api` nicht funktionieren.

- `csp-api-docs` muss in `connect-src` den Ursprung des Realms nennen, weil
  „Authorize“ in Swagger UI dort das Token holt; `worker-src 'self' blob:` und
  `style-src 'unsafe-inline'` sind für ReDoc. Die Vorgabe des Templates kennt
  keinen Realm-Ursprung; der Wert kommt aus `.cookiecutter_all.yaml`.
- `csp-ui` muss in `connect-src` die Ursprünge nennen, mit denen das Frontend
  ursprungsübergreifend spricht: den OIDC-Provider (Token, Userinfo), das
  Backend sowie die Dienste type und unit (die UI liest Beschriftungen,
  Hilfetexte und Einheiten aus deren Vokabularen); und in `frame-src` den
  OIDC-Auth-Endpunkt für die stille Token-Erneuerung. Diese Werte im Gleichlauf
  mit `ifdd_oidc_realm`, `ifdd_be_url`, `ifdd_type_url` und `ifdd_unit_url`
  halten.

Nach einer Änderung die UI und die Keycloak-Konsole in der Browser-Konsole
prüfen und die Richtlinien so weit verschärfen, wie sie noch funktionieren.
{%- else %}

In dieser Instanz aus (`ifdd_proxy_enable_security_headers`): Es gibt keine
`headers.yml`, und Dienste dürfen weder `security-headers@file` noch eine
`csp-*@file`-Middleware nennen; einen Router, der eine fehlende Middleware
nennt, liefert Traefik nicht aus.
{%- endif %}

## Client-Adressen und weitergeleitete Header

{% if trusted -%}
Traefik vertraut `X-Forwarded-*` von {% for ip in trusted %}`{{ ip }}`{{ ", " if not loop.last else "" }}{% endfor %}
(`ifdd_proxy_trusted_ips`) und entfernt die Header bei jeder anderen Quelle.
{%- else -%}
Keinem vorgeschalteten Proxy wird vertraut (`ifdd_proxy_trusted_ips` ist
leer): Traefik entfernt `X-Forwarded-*` aus eingehenden Anfragen und setzt
eigene.
{%- endif %}

Anfrage-Header mit `_` statt `-` (etwa `X_Auth_User`), die manche Server wie
ihre Schreibweise mit `-` behandeln, behandelt jeder Entry Point mit der
Strategie `{{ cookiecutter.ifdd_proxy_alias_headers_strategy }}`
(`ifdd_proxy_alias_headers_strategy`).

## Container

Alle Container laufen mit `no-new-privileges`. Secrets liegen in `.env`
(Modus 0600) und `secrets/` (Modus 0700), beide von Git ausgenommen und auf
der Skip-Liste; `secrets/` ist nur lesend eingebunden, `.env` gar nicht.
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}
oauth2-proxy läuft mit schreibgeschütztem Root-Dateisystem und ohne
veröffentlichten Port; sein Vertrauen in `X-Forwarded-*` beschreibt
{ref}`ifdd-proxy-login-gate`.
{%- endif %}
