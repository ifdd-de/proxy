(ifdd-proxy-setup)=
# Einrichtung
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set own = tls and not le %}
{%- set internal_hosts = cookiecutter.ifdd_proxy_internal_hosts.split(",") | map("trim") | reject("equalto", "") | list %}

## Voraussetzungen

| Was | Warum |
|---|---|
| Docker mit Compose | Traefik{% if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}, der Socket-Proxy{% endif %}{% if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %} und oauth2-proxy{% endif %} laufen als Container |
| freie Host-Ports `{{ cookiecutter.ifdd_proxy_port }}`{% if tls %} und `{{ cookiecutter.ifdd_proxy_tls_port }}`{% endif %} | die einzigen veröffentlichten Ports des Knotens |
| jeder Hostname jedes Dienstes löst für seine Nutzer auf diese Maschine auf | DNS oder `/etc/hosts` der Clients; in den Containern übernehmen die Netz-Aliasse (siehe unten) |
{%- if own %}
| Zertifikate und Schlüssel für diese Hostnamen, oder `openssl` für `adm_01_certs.sh` | eigene Zertifikate (`certs/`) |
{%- elif le %}
| Port 80 dieser Maschine aus dem Internet erreichbar, eine gültige E-Mail-Adresse in `ifdd_proxy_letsencrypt_email` | die HTTP-01-Challenge von Let's Encrypt |
{%- endif %}

## Instanz anlegen

Üblicherweise legt das Meta-Repository alle Instanzen in einem Zug an
(`.adm_meta_01_all.sh`, Schritt `.adm_01_create_services.sh`): Es ruft
`cruft create` mit der gemeinsamen Variablendatei `.cookiecutter_all.yaml`
auf, führt hier `adm_01_certs.sh` aus und kopiert `certs/ca.crt` in die
Dienste, die es brauchen, sowie das Client-Secret von oauth2-proxy aus der
Keycloak-Instanz.

Von Hand, im Verzeichnis der Instanzen, mit der Skip-Liste, die dieses
Template empfiehlt:

```bash
cruft create --no-input --config-file .cookiecutter_all.yaml \
  --skip .env --skip secrets --skip certs --skip letsencrypt \
  --skip logs --skip traefik/private \
  https://github.com/ifdd-de/proxy
```

Die Skip-Liste hält die Dateien der Instanz (Umgebung, Secrets, Schlüssel,
ACME-Zustand, private dynamische Konfiguration) aus jedem späteren
`cruft update` heraus. Das Meta-Repository übergibt `--skip envs --skip .env
--skip secrets`.

## Konfiguration und Secrets

Der Post-Generation-Hook

- schreibt `.env` aus `dotenv.dist` (Modus 0600);
- erzeugt ein Dashboard-Passwort (32 Buchstaben und Ziffern) für den Benutzer
  `{{ cookiecutter.ifdd_proxy_dashboard_user }}`, schreibt es in `.env`
  (`IFDD_PROXY_DASHBOARD_PASSWORD`, nur zum Nachlesen) und die passende
  APR1-Zeile in `secrets/dashboard.htpasswd`;
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}
- erzeugt das Cookie-Secret von oauth2-proxy
  (`secrets/oauth2_proxy_cookie_secret`) und legt eine leere
  `secrets/oauth2_proxy_client_secret` für das Client-Secret aus Keycloak an;
{%- endif %}
- entfernt die Dateien, die die gewählten Optionen nicht brauchen.

Eine vorhandene `secrets/dashboard.htpasswd` bleibt erhalten. `.env` speist
nur die `${...}` der Compose-Dateien und erreicht die Container nie: Traefik
liest jede `TRAEFIK_*`-Variable seiner Umgebung als Konfiguration. Für alles,
was dort hinzukommt, das Präfix `IFDD_PROXY_` beibehalten. Die Einträge stehen
in {ref}`ifdd-proxy-reference`.

Alle übrigen Werte kommen aus den Variablen des Templates; sie stehen mit
ihren Werten und ihrer Bedeutung in {ref}`ifdd-instances-proxy`.

## Interne Hostnamen

Dienste rufen einander unter ihren öffentlichen URLs auf: Das Backend holt die
Signaturschlüssel von Keycloak unter `https://<Keycloak-Host>/...` und
JSON-LD-Kontexte unter `https://<Schema-Host>/...`. In einem Container müssen
diese Namen zu diesem Proxy führen. Docker reicht die `/etc/hosts` des Hosts
nicht an die Container weiter, und ein Host, der die Namen auf `127.0.0.1`
abbildet, schickte jeden Container zu sich selbst.

`ifdd_proxy_internal_hosts` nennt die Namen, die Container im Netz
`{{ cookiecutter.ifdd_proxy_network }}` zu diesem Proxy auflösen
(Netz-Aliasse des Proxy-Containers). Diese Instanz:
{% if internal_hosts %}{% for host in internal_hosts %}`{{ host }}`{{ ", " if not loop.last else "." }}{% endfor %}{% else %}keine.{% endif %}
Jeden Hostnamen eintragen, den ein Dienst bei einem anderen aufruft, und nur
Namen, die dieser Proxy routet: Ein Alias verdeckt für alle Container im Netz
jede andere Auflösung dieses Namens.

Der aufrufende Dienst muss außerdem dem Zertifikat des Proxys vertrauen: Sein
Image übernimmt das CA-Zertifikat beim Bauen aus seinem eigenen
`certs/`-Verzeichnis (siehe die Dokumentation dieses Dienstes).

Aus einem Dienst-Container heraus prüfen, ob ein Name zum Proxy führt:

```bash
docker compose exec <service> getent hosts <host>
docker network inspect {{ cookiecutter.ifdd_proxy_network }} --format {% raw %}'{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'{% endraw %}
```

Die Adresse aus dem ersten Befehl muss die des Proxys sein.

## Zertifikate
{%- if own %}

Das Standardzertifikat und seinen Schlüssel als
`{{ cookiecutter.ifdd_proxy_default_cert_file }}` und
`{{ cookiecutter.ifdd_proxy_default_key_file }}` nach `certs/` legen. Weitere
Zertifikate gehören in `traefik/private/certificates.yml` (dorthin
`certificates.yml.dist` kopieren). Clients, die keinen Servernamen senden
oder einen, den kein Zertifikat abdeckt, werden abgewiesen (`sniStrict`).

Ohne eigene Zertifikate erzeugt `./adm_01_certs.sh` einmalig eine lokale CA
(`certs/ca.crt`, `certs/ca.key`) und das von ihr signierte
Standardzertifikat. Das Zertifikat deckt die internen Hostnamen oben und
`IFDD_PROXY_DASHBOARD_HOST` aus `.env` ab. Das Skript verweigert die Arbeit,
sobald eine der vier Dateien existiert, und rührt eigene Zertifikate daher nie
an; für einen Neuanfang alle vier löschen.

1. Vor dem ersten Start ausführen: `./adm_01_certs.sh`.
2. `certs/ca.crt` im Browser oder Betriebssystem aller vertrauen, die die
   Dienste nutzen.
3. `certs/ca.crt` nach `certs/` jedes Dienstes kopieren, der über diesen Proxy
   einen anderen aufruft, und dessen Image neu bauen.
{%- elif le %}

Traefik bezieht die Zertifikate von Let's Encrypt
({{ "Staging-CA" if cookiecutter.ifdd_proxy_letsencrypt_staging == "y" else "Produktions-CA" }})
über die HTTP-01-Challenge und speichert sie in `letsencrypt/acme.json`; der
Resolver sitzt am Entry Point `websecure`, also bekommt ihn jeder Router.
Jeder Hostname jedes Routers muss auf diese Maschine auflösen und Port 80 aus
dem Internet erreichbar sein. Bis das erste Zertifikat ausgestellt ist,
scheitern HTTPS-Handshakes (`sniStrict` weist das selbstsignierte
Ersatzzertifikat von Traefik ab). Zuerst gegen die Staging-CA testen
(`ifdd_proxy_letsencrypt_staging`): Die Produktions-CA begrenzt
fehlgeschlagene Versuche.
{%- else %}

TLS ist in dieser Instanz aus: Traefik liefert reines HTTP auf Port
`{{ cookiecutter.ifdd_proxy_port }}` und braucht keine Zertifikate. Dienste,
die einander über HTTPS aufrufen, funktionieren damit nicht.
{%- endif %}

## Erster Start

```bash
docker network create {{ cookiecutter.ifdd_proxy_network }}   # einmal je Host, falls noch nicht vorhanden
docker compose -f docker-compose-production.yml up -d
docker compose -f docker-compose-production.yml ps
```

Das Netz ist für jedes Compose-Projekt extern, auch für den Proxy, daher
entfernt kein `down` es, solange andere Dienste angeschlossen sind. `ps`
sollte den Proxy als healthy melden. Das Dashboard liegt unter
`{{ "https" if tls else "http" }}://<Dashboard-Host>/dashboard/`, mit
abschließendem Schrägstrich; die Anmeldung ist `IFDD_PROXY_DASHBOARD_USER` mit
`IFDD_PROXY_DASHBOARD_PASSWORD` aus `.env`.
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}
Mit Login-Gate zuerst Traefik allein starten; siehe
{ref}`ifdd-proxy-operations`.
{%- endif %}

## Lokale Entwicklung

```bash
docker compose -f docker-compose-development.yml up -d
```

Traefik liefert sein selbstsigniertes Standardzertifikat aus, Browser warnen
also, und `sniStrict` ist deshalb aus. `secrets/dashboard.htpasswd` braucht
das Dashboard wie in Produktion. Kein Client kann dieses Zertifikat prüfen,
daher scheitern Dienste, die einander über den Proxy per HTTPS aufrufen
(Token-Prüfung, JSON-LD-Kontexte), in der Entwicklung; dafür die
Produktionsvariante nehmen. Die Entwicklungsvariante bindet weder `certs/`
noch `traefik/private/` ein und nutzt nie Let's Encrypt.

## Einen Dienst anbinden

Ein Dienst tritt dem Netz bei und erklärt seinen Router mit Labels:

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

`api` und `api.example.org` sind Beispiele. Container ohne
`traefik.enable=true` werden ignoriert (`exposedByDefault: false`).

- **Keine `tls`-Labels am Router.** TLS{% if le %} und der Zertifikats-Resolver{% endif %}
  sind am Entry Point gesetzt. Ein Router mit einem eigenen `tls`-Abschnitt,
  auch nur `...routers.api.tls=true`, ersetzt diese Konfiguration vollständig.
  Geprüft mit Traefik v3.7.13: Ein solcher Router hat danach überhaupt keine
  TLS-Konfiguration.
- **Kein `entrypoints`-Label nötig.** Router ohne eines hängen am
  Standard-Entry-Point (`websecure`, ohne TLS `web`).
{%- if cookiecutter.ifdd_proxy_enable_security_headers == "y" %}
- **Sicherheits-Header** werden je Router angehängt; welche CSP zu welcher Art
  Host passt, steht in {ref}`ifdd-proxy-security`.
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_dos_baseline == "y" and cookiecutter.ifdd_proxy_dos_enable_buffering == "y" %}
- **Grenze für Request-Bodies, nur auf Wunsch:** `dos-buffering@file` zu den
  Middlewares des Routers hinzufügen. Sie gehört nicht zum globalen
  DoS-Grundschutz: Am Entry Point umfasst sie auch das Dashboard, und mit
  v3.7.13 scheitert dann jede Dashboard-Anfrage. Buffering hält die ganze
  Anfrage, bevor es sie weiterreicht; für Streaming-Uploads passt das nicht.
{%- endif %}
