(ifdd-proxy-login-gate)=
# Login gate (oauth2-proxy)
{%- set o2 = cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

oauth2-proxy is a shared login gate for services without a login of their
own: a service opts in per router with a forwardAuth middleware, and chooses
the Keycloak group whose members may pass. Browsers without a session are
sent to Keycloak; signed-in users outside the group get 403; API clients
without a session get 401.
{%- if not o2 %}

**The login gate is off in this instance** (`ifdd_proxy_enable_oauth2_proxy`).
The section {ref}`ifdd-proxy-login-gate-enable` describes how to turn it on.
{%- endif %}

## Keycloak

oauth2-proxy uses one client of the realm{% if o2 %}
(`IFDD_PROXY_OIDC_CLIENT_ID` in the realm `IFDD_PROXY_OIDC_ISSUER`, see
`.env`){% endif %}:

1. Client: OpenID Connect, client authentication on, standard flow on;
   valid redirect URIs `https://<service host>/oauth2/callback` for every
   host that uses the gate. Its secret goes into
   `secrets/oauth2_proxy_client_secret`.
2. Client scope `groups` with a mapper "Group Membership", claim name
   `groups`, **"Full group path" off** (otherwise groups arrive as `/name`
   and `allowed_groups=name` never matches), added to the client.
3. Audience: if tokens lack the client in `aud`, add an "Audience" mapper
   for the client.
4. Users who may pass: members of the group, with an **e-mail address marked
   as verified**. Without an e-mail address oauth2-proxy refuses the login,
   with an unverified one as well.

The `ifdd-de/keycloak` template creates the client, the scope and the mapper
of steps 1 to 3 with its realm; the secret is
`IFDD_KEYCLOAK_PROXY_CLIENT_SECRET` in its `.env`. The meta repository copies
it into `secrets/oauth2_proxy_client_secret`.

## Trusting the realm

oauth2-proxy calls the realm itself (discovery, token, keys).
{%- if o2 and cookiecutter.ifdd_proxy_oauth2_proxy_ca_file %} It trusts
`certs/{{ cookiecutter.ifdd_proxy_oauth2_proxy_ca_file }}` in addition to the
public CAs; that file must exist before the start (`adm_01_certs.sh` creates
`ca.crt`). Only that file is mounted, read-only; a missing file is an error,
not an empty directory.
{%- else %} By default it trusts the public CAs only; if the realm's
certificate comes from a CA of your own, set
`ifdd_proxy_oauth2_proxy_ca_file` (e.g. `ca.crt`), or oauth2-proxy stops at
start with `x509: certificate signed by unknown authority`.
{%- endif %}

## Wiring a service

Labels of a service behind the proxy (`ifdd-de/wf` has a complete example):

```yaml
- "traefik.http.middlewares.<svc>-sso.forwardauth.address=http://oauth2-proxy:4180/?allowed_groups=<group>"
- "traefik.http.middlewares.<svc>-sso.forwardauth.trustForwardHeader=true"
- "traefik.http.routers.<svc>.middlewares=<svc>-sso"
- "traefik.http.routers.<svc>-oauth2.rule=Host(`<host>`) && PathPrefix(`/oauth2/`)"
- "traefik.http.routers.<svc>-oauth2.service=oauth2-proxy@docker"
```

The forwardAuth address goes to the container directly. The router
`<svc>-oauth2` serves the login callback on the service's host; without it
the fallback router `oauth2-proxy` (`PathPrefix(/oauth2/)`, priority 1)
takes over, which exists only while oauth2-proxy is healthy. Sign-out:
`https://<host>/oauth2/sign_out`.

## Operation

- Health check: `wget` on `/ready` inside the container, so the image must be
  an `-alpine` variant. oauth2-proxy stops when it cannot reach the realm at
  start and is restarted, so it turns healthy only once Keycloak answers.
- Start order: Traefik, then Keycloak, then the whole proxy project
  ({ref}`ifdd-proxy-operations`).
- The cookie secret (`secrets/oauth2_proxy_cookie_secret`, 32 random bytes,
  URL-safe base64) signs the sessions; replacing it signs everybody out.
- oauth2-proxy trusts `X-Forwarded-*` from every source (it warns about it at
  start). It has no published port and is only reachable on
  `{{ cookiecutter.ifdd_proxy_network }}`; every container on that network
  could therefore set those headers. `OAUTH2_PROXY_TRUSTED_PROXY_IPS` can
  restrict this once the address range of the network is fixed.

(ifdd-proxy-login-gate-enable)=
## Enabling it in an existing instance

`cruft update` renders with the context in `.cruft.json`, and `.env` and
`secrets/` are on the skip list. So:

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

Without the secret files Docker would mount empty directories in their
place. The login gate needs TLS; the pre-generation hook refuses it without.

An instance that already runs oauth2-proxy with a distroless image needs the
`-alpine` image on update, or the pre-generation hook refuses it:

```bash
cruft update -y --variables-to-update \
  '{"ifdd_proxy_oauth2_proxy_image": "{{ cookiecutter.ifdd_proxy_oauth2_proxy_image }}"}'
```

```{note}
Not tested: the login gate with a real Keycloak and the container image. The
flow was checked with the oauth2-proxy 7.15.5 binary, Traefik v3.7.13 and a
simulated realm (see the honesty notes of the template `ifdd-de/proxy`).
```
