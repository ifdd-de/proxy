(ifdd-proxy-login-gate)=
# Login-Gate (oauth2-proxy)
{%- set o2 = cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

oauth2-proxy ist ein gemeinsames Login-Gate für Dienste ohne eigene
Anmeldung: Ein Dienst schließt sich je Router mit einer
forwardAuth-Middleware an und wählt die Keycloak-Gruppe, deren Mitglieder
durchdürfen. Browser ohne Sitzung werden zu Keycloak geschickt; angemeldete
Benutzer außerhalb der Gruppe bekommen 403; API-Clients ohne Sitzung 401.
{%- if not o2 %}

**Das Login-Gate ist in dieser Instanz aus** (`ifdd_proxy_enable_oauth2_proxy`).
Der Abschnitt {ref}`ifdd-proxy-login-gate-enable` beschreibt, wie man es
einschaltet.
{%- endif %}

## Keycloak

oauth2-proxy nutzt einen Client des Realms{% if o2 %}
(`IFDD_PROXY_OIDC_CLIENT_ID` im Realm `IFDD_PROXY_OIDC_ISSUER`, siehe
`.env`){% endif %}:

1. Client: OpenID Connect, Client Authentication an, Standard Flow an;
   gültige Redirect-URIs `https://<Dienst-Host>/oauth2/callback` für jeden
   Host, der das Gate nutzt. Sein Secret gehört nach
   `secrets/oauth2_proxy_client_secret`.
2. Client Scope `groups` mit einem Mapper „Group Membership“, Claim-Name
   `groups`, **„Full group path“ aus** (sonst kommen Gruppen als `/name` an
   und `allowed_groups=name` passt nie), dem Client hinzugefügt.
3. Audience: Fehlt der Client in `aud` der Tokens, einen Mapper „Audience“
   für den Client anlegen.
4. Benutzer, die durchdürfen: Mitglieder der Gruppe mit einer **als bestätigt
   markierten E-Mail-Adresse**. Ohne E-Mail-Adresse weist oauth2-proxy die
   Anmeldung ab, mit einer unbestätigten ebenso.

Das Template `ifdd-de/keycloak` legt Client, Scope und Mapper aus den
Schritten 1 bis 3 mit seinem Realm an; das Secret ist
`IFDD_KEYCLOAK_PROXY_CLIENT_SECRET` in dessen `.env`. Das Meta-Repository
kopiert es nach `secrets/oauth2_proxy_client_secret`.

## Vertrauen zum Realm

oauth2-proxy ruft den Realm selbst auf (Discovery, Token, Schlüssel).
{%- if o2 and cookiecutter.ifdd_proxy_oauth2_proxy_ca_file %} Er vertraut
`certs/{{ cookiecutter.ifdd_proxy_oauth2_proxy_ca_file }}` zusätzlich zu den
öffentlichen CAs; die Datei muss vor dem Start existieren (`adm_01_certs.sh`
erzeugt `ca.crt`). Nur diese Datei wird eingebunden, nur lesend; fehlt sie,
ist das ein Fehler, kein leeres Verzeichnis.
{%- else %} Standardmäßig vertraut er nur den öffentlichen CAs; stammt das
Zertifikat des Realms von einer eigenen CA, `ifdd_proxy_oauth2_proxy_ca_file`
setzen (z. B. `ca.crt`), sonst bricht oauth2-proxy beim Start mit
`x509: certificate signed by unknown authority` ab.
{%- endif %}

## Einen Dienst anbinden

Labels eines Dienstes hinter dem Proxy (`ifdd-de/wf` hat ein vollständiges
Beispiel):

```yaml
- "traefik.http.middlewares.<svc>-sso.forwardauth.address=http://oauth2-proxy:4180/?allowed_groups=<group>"
- "traefik.http.middlewares.<svc>-sso.forwardauth.trustForwardHeader=true"
- "traefik.http.routers.<svc>.middlewares=<svc>-sso"
- "traefik.http.routers.<svc>-oauth2.rule=Host(`<host>`) && PathPrefix(`/oauth2/`)"
- "traefik.http.routers.<svc>-oauth2.service={{ cookiecutter.ifdd_proxy_prj_slug }}-oauth2-proxy@docker"
```

Die forwardAuth-Adresse geht direkt an den Container. Der Router
`<svc>-oauth2` bedient den Login-Callback auf dem Host des Dienstes; ohne ihn
übernimmt der Ersatz-Router `{{ cookiecutter.ifdd_proxy_prj_slug }}-oauth2-proxy` (`PathPrefix(/oauth2/)`, Priorität
1), den es nur gibt, solange oauth2-proxy healthy ist. Abmelden:
`https://<host>/oauth2/sign_out`.

## Betrieb

- Healthcheck: `wget` auf `/ready` im Container, daher muss das Image eine
  `-alpine`-Variante sein. oauth2-proxy beendet sich, wenn er den Realm beim
  Start nicht erreicht, und wird neu gestartet; healthy wird er also erst,
  wenn Keycloak antwortet.
- Startreihenfolge: Traefik, dann Keycloak, dann das ganze Proxy-Projekt
  ({ref}`ifdd-proxy-operations`).
- Das Cookie-Secret (`secrets/oauth2_proxy_cookie_secret`, 32 Zufallsbytes,
  URL-sicheres Base64) signiert die Sitzungen; wer es ersetzt, meldet alle
  ab.
- oauth2-proxy vertraut `X-Forwarded-*` von jeder Quelle (er warnt beim Start
  davor). Er hat keinen veröffentlichten Port und ist nur im Netz
  `{{ cookiecutter.ifdd_proxy_network }}` erreichbar; jeder Container in diesem
  Netz könnte diese Header also setzen. `OAUTH2_PROXY_TRUSTED_PROXY_IPS` kann
  das einschränken, sobald der Adressbereich des Netzes feststeht.

(ifdd-proxy-login-gate-enable)=
## In einer bestehenden Instanz einschalten

`cruft update` rendert mit dem Kontext aus `.cruft.json`, und `.env` sowie
`secrets/` stehen auf der Skip-Liste. Daher:

```bash
cruft update -y --variables-to-update \
  '{"ifdd_proxy_enable_oauth2_proxy": "y", "ifdd_proxy_oidc_issuer": "<realm URL>", "ifdd_proxy_oauth2_proxy_ca_file": "ca.crt"}'
# add to .env:   IFDD_PROXY_OIDC_ISSUER=<realm URL>
#                IFDD_PROXY_OIDC_CLIENT_ID=<client id>
python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode(),end='')" \
  > secrets/oauth2_proxy_cookie_secret
chmod 644 secrets/oauth2_proxy_cookie_secret
printf '%s' '<client secret from Keycloak>' > secrets/oauth2_proxy_client_secret
```

Ohne die Secret-Dateien bände Docker an ihrer Stelle leere Verzeichnisse ein.
Das Login-Gate braucht TLS; ohne weist der Pre-Generation-Hook es ab.

Eine Instanz, die oauth2-proxy schon mit einem Distroless-Image betreibt,
braucht beim Update das `-alpine`-Image, sonst weist der Pre-Generation-Hook
es ab:

```bash
cruft update -y --variables-to-update \
  '{"ifdd_proxy_oauth2_proxy_image": "{{ cookiecutter.ifdd_proxy_oauth2_proxy_image }}"}'
```

```{note}
Nicht getestet: das Login-Gate mit einem echten Keycloak und das
Container-Image. Der Ablauf wurde mit dem Binary von oauth2-proxy 7.15.5,
Traefik v3.7.13 und einem simulierten Realm geprüft (siehe die Honesty notes
des Templates `ifdd-de/proxy`).
```
