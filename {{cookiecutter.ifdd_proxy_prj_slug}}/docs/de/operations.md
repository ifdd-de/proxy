(ifdd-proxy-operations)=
# Betrieb
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set own = tls and not le %}
{%- set dos = cookiecutter.ifdd_proxy_enable_dos_baseline == "y" %}
{%- set o2 = cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

## Starten, Stoppen, Reihenfolge

```bash
docker compose -f docker-compose-production.yml up -d
docker compose -f docker-compose-production.yml ps
docker compose -f docker-compose-production.yml down     # das Netz bleibt
```

Der Proxy kommt auf einem Knoten zuerst: Jeder andere Dienst tritt seinem Netz
bei und erreicht Keycloak und den Schema-Dienst über ihn.
{%- if o2 %}
oauth2-proxy braucht beim Start einen erreichbaren Realm, und Keycloak liegt
selbst hinter Traefik. Daher Traefik allein starten, dann Keycloak, dann das
ganze Projekt:

```bash
docker compose -f docker-compose-production.yml up -d --wait proxy
# die Keycloak-Instanz starten und warten, bis sie healthy ist
docker compose -f docker-compose-production.yml up -d --wait
```
{%- endif %}

`.adm_03_up_services.sh` aus dem Meta-Repository startet alle Dienste in
dieser Reihenfolge.

## Healthchecks

| Container | Prüfung | Intervall |
|---|---|---|
| `proxy` | `traefik healthcheck` gegen den Ping-Entry-Point (`127.0.0.1:8082`, nur Loopback) | 30 s, Timeout 5 s, 3 Versuche, Startphase 10 s |
{%- if o2 %}
| `oauth2-proxy` | `wget` auf `http://127.0.0.1:4180/ready` | 15 s, Timeout 5 s, 5 Versuche, Startphase 30 s |
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
| `socket-proxy` | keine | |
{%- endif %}

Traefik ignoriert Container, die (noch) nicht healthy sind: Ihre Router
fehlen, bis der Healthcheck besteht.

## Änderungen übernehmen

Die statische Konfiguration (`traefik/traefik.yml`) braucht immer einen
Neustart. Der File-Provider beobachtet `/etc/traefik/dynamic`, aber in Tests
mit v3.7.13 lösten nur Änderungen direkt in diesem Verzeichnis ein Neuladen
aus, nicht Änderungen in seinen Unterverzeichnissen, in denen alle Mounts
liegen. Daher nach jeder Änderung der Konfiguration, von
`secrets/dashboard.htpasswd` oder der Dateien in `certs/`:

```bash
docker compose -f docker-compose-production.yml restart proxy
```

Labels der Dienste liest Traefik über die Docker-API; sie wirken, sobald der
Container des Dienstes neu erzeugt ist. Der Proxy braucht dafür keinen
Neustart.

## Logs

```bash
docker compose -f docker-compose-production.yml logs -f proxy
tail -f logs/access.log
```

Das Level des Traefik-Logs ist `{{ cookiecutter.ifdd_proxy_log_level }}`
(`ifdd_proxy_log_level`). Das Access-Log geht nach `logs/access.log` und wird
in Blöcken von bis zu 500 Zeilen geschrieben (`bufferingSize`); die neuesten
Anfragen erscheinen daher unter Umständen verzögert. Das Template richtet
keine Rotation des Access-Logs ein; `logs/` wächst, bis es rotiert oder
geleert wird.

Beim Start meldet Traefik v3.7.13 eine Warnung, dass es manche kodierten
Zeichen in Anfragepfaden abweisen kann; sie ist erwartet.

## Ressourcen

| Container | Grenze | Neustart |
|---|---|---|
| `proxy` | Speicher `{{ cookiecutter.ifdd_proxy_memory_limit }}` (`ifdd_proxy_memory_limit`) | `always` |
{%- if o2 %}
| `oauth2-proxy` | Speicher `128M` | `always` |
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
| `socket-proxy` | keine | `always` |
{%- endif %}

Die Entwicklungsvariante startet mit `unless-stopped` neu und hat keine
Speichergrenze.

```{note}
Nicht getestet: ob die Speichergrenze zu echtem Verkehr passt. Sie ist die
Vorgabe des Templates, kein gemessener Wert.
```

## DoS-Grundschutz
{%- if dos %}

Am öffentlichen Entry Point hängen ein Ratenlimit (`dos-ratelimit`, antwortet
mit 429) und eine Grenze gleichzeitiger Anfragen (`dos-inflight`), beide je
Quelladresse, dazu Grenzen für Header-Größe, HTTP/2-Streams und Timeouts.

| Einstellung | Hier |
|---|---|
| Anfragen je Zeitraum (Durchschnitt, Nachfüllen) | {{ cookiecutter.ifdd_proxy_dos_rate_average }} je {{ cookiecutter.ifdd_proxy_dos_rate_period }} |
| Burst | {{ cookiecutter.ifdd_proxy_dos_rate_burst }} |
| gleichzeitige Anfragen je Quelle | {{ cookiecutter.ifdd_proxy_dos_inflight_amount }} |
| IPv6-Quellen zusammengefasst nach Präfix | /{{ cookiecutter.ifdd_proxy_dos_ipv6_subnet }} |
| maximale Header-Größe | {{ cookiecutter.ifdd_proxy_dos_max_header_bytes }} Byte |
| HTTP/2-Streams je Verbindung | {{ cookiecutter.ifdd_proxy_dos_h2_max_streams }} |
| Lese-, Schreib-, Leerlauf-Timeout | {{ cookiecutter.ifdd_proxy_dos_read_timeout }}, {{ cookiecutter.ifdd_proxy_dos_write_timeout }}, {{ cookiecutter.ifdd_proxy_dos_idle_timeout }} |
{%- if cookiecutter.ifdd_proxy_dos_enable_buffering == "y" %}
| Request-Body, auf Wunsch je Router (`dos-buffering`) | {{ cookiecutter.ifdd_proxy_dos_max_request_body_bytes }} Byte, davon {{ cookiecutter.ifdd_proxy_dos_mem_request_body_bytes }} im Speicher |
{%- endif %}

**Die Werte sind Syntaxbeispiele, keine Empfehlungen.** Sie wurden gegen
keine Last gemessen. Sie aus Lasttests der Dienste hinter diesem Proxy
ableiten und bedenken, dass der Schreib-Timeout auch langsame Downloads und
lang laufende Antworten abschneidet.

Quelladresse:

- Ohne vertrauenswürdigen Proxy davor (`ifdd_proxy_trusted_ips` leer) nutzen
  die Grenzen die Adresse der TCP-Verbindung. `X-Forwarded-For` wird dafür
  nicht beachtet und aus nicht vertrauenswürdigen Anfragen entfernt, bevor
  sie einen Dienst erreichen.
- Mit vertrauenswürdigem Proxy davor nutzen die Grenzen den rechtesten
  Eintrag von `X-Forwarded-For`. Clients, die diesen Proxy umgehen, kommen
  ohne den Header an und teilen sich einen Topf; durch Fälschen öffnen sie
  keine neuen.
- Nicht geprüft: Mit Dockers Userland-Proxy (Standard für veröffentlichte
  Ports, besonders über IPv6) sieht Traefik womöglich das Docker-Gateway
  statt des Clients. Dann teilen sich alle Clients einen Topf. Die
  Client-Adressen in `logs/access.log` prüfen, bevor man sich auf die Grenzen
  verlässt.
{%- else %}

In dieser Instanz aus (`ifdd_proxy_enable_dos_baseline`): kein Ratenlimit,
keine Grenze gleichzeitiger Anfragen, keine Grenzen am Entry Point über die
Vorgaben von Traefik hinaus.
{%- endif %}

## Zertifikate
{%- if own %}

`adm_01_certs.sh` stellt die CA für 3650 Tage und das Standardzertifikat für
825 Tage aus (die längste Gültigkeit, die Apple-Plattformen für
TLS-Serverzertifikate annehmen). Ablaufdatum prüfen:

```bash
openssl x509 -in certs/{{ cookiecutter.ifdd_proxy_default_cert_file }} -noout -enddate
```

Das Skript erneuert nicht: Es verweigert die Arbeit, solange eine seiner vier
Dateien existiert. Ein Neuanfang erzeugt eine neue CA, die jeder Browser,
jedes Betriebssystem und jedes Dienst-Image, das der alten vertraute, erneut
bekommen muss. Eigene Zertifikate werden außerhalb dieser Instanz erneuert;
die Dateien ersetzen und den Proxy neu starten. Ein neuer Hostname im
Zertifikat braucht dieselben Schritte.
{%- elif le %}

Traefik erneuert die Zertifikate von Let's Encrypt selbst und hält sie in
`letsencrypt/acme.json`. Die Datei nicht löschen: Sie enthält das ACME-Konto
und die Zertifikate, und sie alle neu anzufordern zählt gegen die
Ratenlimits von Let's Encrypt.

```{note}
Nicht getestet: Ausstellung und Erneuerung durch Let's Encrypt (kein Zugang
zu den ACME-Servern beim Bau des Templates).
```
{%- else %}

Keine: TLS ist in dieser Instanz aus.
{%- endif %}

## Sicherung

| Pfad | Inhalt |
|---|---|
| `.env` | Dashboard-Host, Host-Ports, Dashboard-Anmeldung{% if o2 %}, Realm und Client von oauth2-proxy{% endif %} |
| `secrets/` | `dashboard.htpasswd`{% if o2 %}, Cookie- und Client-Secret von oauth2-proxy{% endif %} |
{%- if own %}
| `certs/` | Zertifikate und Schlüssel, darunter der CA-Schlüssel `ca.key`, wenn `adm_01_certs.sh` ihn erzeugt hat |
{%- elif le %}
| `letsencrypt/acme.json` | ACME-Konto und Zertifikate mit ihren Schlüsseln |
{%- endif %}
| `traefik/private/` | instanzeigene dynamische Konfiguration |

Alles Übrige kommt aus dem Template und aus Git. Die Pfade oben enthalten
Secrets und private Schlüssel: Die Sicherung so gut schützen wie den Host.

```{note}
Nicht getestet: das Wiederherstellen dieser Dateien auf einem anderen Host.
```

## Aktualisieren

Neue Template-Stände kommen mit `cruft update`; die Skip-Liste lässt die Pfade
oben unberührt. Image-Versionen: siehe {ref}`ifdd-proxy-build-release`. Nach
jedem Update die Tests laufen lassen und den Proxy neu starten.
