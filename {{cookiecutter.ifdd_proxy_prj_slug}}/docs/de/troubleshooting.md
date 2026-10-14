(ifdd-proxy-troubleshooting)=
# Fehlersuche

Bekannte Fehlerbilder aus Einrichtungen von IFDD-Knoten. Beginnen mit
`docker compose -f docker-compose-production.yml logs proxy`, dem Dashboard
(welche Router es gibt, welche Fehler haben) und `logs/access.log`.

## Dashboard

| Symptom | Ursache | Abhilfe |
|---|---|---|
| `/dashboard/` antwortet 404 | `secrets/dashboard.htpasswd` fehlt: Traefik kann die Middleware nicht bauen und hängt den Router aus | Datei anlegen (siehe {ref}`ifdd-proxy-security`), Proxy neu starten |
| `/dashboard` antwortet 404, `/dashboard/` funktioniert | der Pfad braucht den abschließenden Schrägstrich | `/dashboard/` verwenden |
| ein neues Passwort wird abgewiesen, das alte gilt noch | Traefik liest die Benutzerdatei nur beim Start | Proxy neu starten |
| der Browser fragt immer wieder nach dem Passwort, obwohl `curl -u <user> https://<Dashboard-Host>/dashboard/` gelingt | der Browser sendet noch alte Anmeldedaten | privates Fenster oder Browser neu starten |
| jede Dashboard-Anfrage scheitert, das Log zeigt eine abgefangene Panic `invalid WriteHeader code 0` | `dos-buffering` am Entry Point (umfasst das Dashboard; Traefik v3.7.13) | `dos-buffering` nur je Router anhängen |

## Routing und TLS

| Symptom | Ursache | Abhilfe |
|---|---|---|
| ein Dienst bekommt 404 | kein Router: `traefik.enable=true` fehlt, der Container ist nicht in `{{ cookiecutter.ifdd_proxy_network }}`, er ist noch nicht healthy, oder eine genannte Middleware existiert nicht | Router im Dashboard und Labels des Dienstes prüfen |
| ein Dienst wird ohne TLS ausgeliefert oder verliert sein Zertifikat | der Dienst setzt ein `tls`-Label am Router | jedes `...routers.<name>.tls...`-Label entfernen |
| der TLS-Handshake scheitert für einen Hostnamen | `sniStrict`: kein Zertifikat deckt den Namen ab, oder der Client sendet keinen Servernamen | den Namen in ein Zertifikat aufnehmen (`traefik/private/certificates.yml` oder `adm_01_certs.sh` neu beginnen), neu starten |
| eine Änderung in `traefik/dynamic/...` wirkt nicht | der File-Provider lädt Änderungen in den eingebundenen Unterverzeichnissen nicht neu | Proxy neu starten |
| Browser warnen in der Entwicklung vor dem Zertifikat | die Entwicklungsvariante liefert das selbstsignierte Zertifikat von Traefik | erwartet; für HTTPS zwischen Diensten die Produktionsvariante nehmen |
| Traefik meldet beim Start eine Warnung zu kodierten Zeichen | erwartet mit v3.7.13 | keine |
{%- if cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
| HTTPS-Handshakes scheitern nach dem ersten Start | noch kein Zertifikat ausgestellt (`sniStrict` weist das Ersatzzertifikat ab) | prüfen, ob die Hostnamen auf diese Maschine auflösen und Port 80 aus dem Internet erreichbar ist; das Log zeigt die ACME-Fehler |
{%- endif %}

## Aufrufe zwischen Diensten

| Symptom | Ursache | Abhilfe |
|---|---|---|
| ein Dienst erreicht einen anderen unter dessen öffentlicher URL nicht, oder erreicht sich selbst | der Hostname ist kein Netz-Alias des Proxys | ihn in `ifdd_proxy_internal_hosts` eintragen (`cruft update --variables-to-update`), den Proxy-Container neu erzeugen |
| `CERTIFICATE_VERIFY_FAILED` oder `x509: certificate signed by unknown authority` in einem Dienst | der Dienst vertraut dem Zertifikat des Proxys nicht | `certs/ca.crt` nach `certs/` dieses Dienstes kopieren, sein Image neu bauen |
| HTTPS zwischen Diensten scheitert nur in der Entwicklung | das selbstsignierte Zertifikat der Entwicklungsvariante | die Produktionsvariante nehmen |

## Grenzen

| Symptom | Ursache | Abhilfe |
|---|---|---|
| 429 Too Many Requests | das Ratenlimit des DoS-Grundschutzes | Client-Adressen in `logs/access.log` prüfen; hinter Dockers Userland-Proxy teilen sich womöglich alle Clients einen Topf |
| 413 bei Uploads | die Body-Grenze von `dos-buffering` an diesem Router | `ifdd_proxy_dos_max_request_body_bytes` erhöhen oder `dos-buffering` vom Router nehmen |
| langsame Downloads oder lange Antworten brechen ab | der Schreib-Timeout des Entry Points | `ifdd_proxy_dos_write_timeout` erhöhen |
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

## Login-Gate

| Symptom | Ursache | Abhilfe |
|---|---|---|
| oauth2-proxy startet immer wieder neu, Log: `x509: certificate signed by unknown authority` | er vertraut dem Zertifikat des Realms nicht | `ifdd_proxy_oauth2_proxy_ca_file` setzen (z. B. `ca.crt`) |
| oauth2-proxy wird nicht healthy | der Realm ist beim Start nicht erreichbar | Traefik, dann Keycloak, dann das ganze Projekt starten ({ref}`ifdd-proxy-operations`) |
| `/oauth2/` antwortet 404 auf einem Host ohne eigenen `/oauth2/`-Router | der Ersatz-Router fehlt, solange oauth2-proxy nicht healthy ist | auf den Healthcheck warten; dem Dienst einen eigenen `/oauth2/`-Router geben |
| Anmeldung abgewiesen: `neither the id_token nor the profileURL set an email` | der Benutzer hat keine E-Mail-Adresse | in Keycloak eine setzen |
| Anmeldung abgewiesen: `email in id_token ... isn't verified` | die Adresse ist nicht als bestätigt markiert | „Email verified“ für den Benutzer einschalten |
| Mitglieder der Gruppe bekommen 403 | der Gruppen-Claim trägt den vollen Pfad (`/name`) | „Full group path“ im Mapper ausschalten |
| der Container scheitert an einem Verzeichnis, wo eine Secret-Datei erwartet wird | `secrets/oauth2_proxy_*` existierte nicht; Docker hat leere Verzeichnisse eingebunden | die Dateien anlegen ({ref}`ifdd-proxy-login-gate`) |
{%- endif %}
