(ifdd-proxy-build-release)=
# Bauen und Freigeben

## Images

Der Proxy baut kein eigenes Image; er betreibt Upstream-Images, in die die
Konfiguration dieser Instanz nur lesend eingebunden wird.

| Container | Image | Vorhanden |
|---|---|---|
| `proxy` | `traefik:{{ cookiecutter.ifdd_proxy_traefik_version }}` | immer |
| `socket-proxy` | `{{ cookiecutter.ifdd_proxy_socket_proxy_image }}` | {{ "ja" if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" else "nein (`ifdd_proxy_enable_socket_proxy`)" }} |
| `oauth2-proxy` | `{{ cookiecutter.ifdd_proxy_oauth2_proxy_image }}` | {{ "ja" if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" else "nein (`ifdd_proxy_enable_oauth2_proxy`)" }} |

Das oauth2-proxy-Image muss eine `-alpine`-Variante sein: Der Healthcheck
ruft `wget` auf, und die Standard-Images von oauth2-proxy sind distroless.
Mit eingeschaltetem Login-Gate weist der Pre-Generation-Hook andere Images
ab.

```bash
docker compose -f docker-compose-production.yml pull
```

## Versionen

Die Image-Tags sind Template-Variablen. Um einen in einer bestehenden Instanz
zu ändern, ihn über cruft setzen, damit `.cruft.json` den Wert behält:

```bash
cruft update -y --variables-to-update '{"ifdd_proxy_traefik_version": "<tag>"}'
docker compose -f docker-compose-production.yml pull
docker compose -f docker-compose-production.yml up -d
```

Das Template ist mit Traefik `v3.7.13` getestet. Eine neue Traefik-Version
kann Verhalten ändern, auf das die Konfiguration baut (TLS-Vererbung an
Router, das Dashboard mit Buffering, Neuladen des File-Providers); nach einem
Update {ref}`ifdd-proxy-troubleshooting` und die Tests unten prüfen.

## Tests

```bash
pip install -r tests/requirements.txt
pytest -q tests                      # statische Prüfungen, ohne Docker
tests/smoke.sh development           # startet den Container und prüft ihn
tests/smoke.sh production            # nur mit eigenen Zertifikaten
```

Die statischen Prüfungen lesen die gerenderte Konfiguration: Das Dashboard
wird nie ohne Anmeldung ausgeliefert, nichts aus `.env` erreicht den
Container, jeder eingebundene Host-Pfad existiert, TLS und `sniStrict` je
Umgebung, der DoS-Grundschutz und der Platz des Bufferings, die internen
Hostnamen in beiden Compose-Dateien, das Zertifikatsskript, die
Header-Middlewares und die Einstellungen von oauth2-proxy. `tests/smoke.sh`
startet den echten Container und prüft von außen Health, die Umleitung von
HTTP auf HTTPS und die Dashboard-Anmeldung; jede Datei, die es anlegt,
entfernt es wieder. Bei Let's Encrypt überspringt sich die Produktionsvariante.

## CI der Instanz

`.github/workflows/ci.yml` läuft bei jedem Push und Pull Request:

- **Configuration**: die statischen Prüfungen und `docker compose config` für
  beide Compose-Dateien (mit den Vorgaben aus `dotenv.dist`);
- **Smoke test (development)**: `tests/smoke.sh development`;
- **Template drift**: `cruft check` und `cruft diff`, beide nur informativ.
  Was `cruft diff` zeigt, gehört entweder zurück ins Template oder auf die
  Skip-Liste.

## Freigabe

Es gibt keinen Release-Workflow, weil kein Image gebaut wird. Ein Release des
Proxys ist ein neuer Stand dieses Repositorys plus `docker compose ... up -d`
auf dem Host.
