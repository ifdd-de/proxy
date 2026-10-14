(ifdd-proxy-troubleshooting)=
# Troubleshooting

Known failure patterns, from setups of IFDD nodes. Start with
`docker compose -f docker-compose-production.yml logs proxy`, the dashboard
(which routers exist, which have errors) and `logs/access.log`.

## Dashboard

| Symptom | Cause | Remedy |
|---|---|---|
| `/dashboard/` answers 404 | `secrets/dashboard.htpasswd` is missing: Traefik cannot build the middleware and unmounts the router | create the file (see {ref}`ifdd-proxy-security`), restart the proxy |
| `/dashboard` answers 404, `/dashboard/` works | the path needs the trailing slash | use `/dashboard/` |
| a new password is refused, the old one still works | Traefik reads the users file only at start | restart the proxy |
| the browser keeps asking for the password although `curl -u <user> https://<dashboard host>/dashboard/` succeeds | the browser still sends old credentials | private window, or restart the browser |
| every dashboard request fails, the log shows a recovered panic `invalid WriteHeader code 0` | `dos-buffering` attached to the entry point (wraps the dashboard; Traefik v3.7.13) | attach `dos-buffering` per router only |

## Routing and TLS

| Symptom | Cause | Remedy |
|---|---|---|
| a service gets 404 | no router: `traefik.enable=true` missing, the container is not on `{{ cookiecutter.ifdd_proxy_network }}`, it is not healthy yet, or a middleware it names does not exist | check the router in the dashboard and the labels of the service |
| a service is served without TLS, or loses its certificate | the service sets a router `tls` label | remove every `...routers.<name>.tls...` label |
| the TLS handshake fails for one host name | `sniStrict`: no certificate covers that name, or the client sends no server name | add the name to a certificate (`traefik/private/certificates.yml`, or start `adm_01_certs.sh` over), restart |
| a change in `traefik/dynamic/...` has no effect | the file provider does not reload changes in the mounted subdirectories | restart the proxy |
| browsers warn about the certificate in development | the development variant serves Traefik's self-signed certificate | expected; use the production variant for HTTPS between services |
| Traefik logs a warning about encoded characters at start | expected with v3.7.13 | none |
{%- if cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
| HTTPS handshakes fail after the first start | no certificate issued yet (`sniStrict` refuses the fallback certificate) | check that the host names resolve to this machine and port 80 is reachable from the internet; the log shows the ACME errors |
{%- endif %}

## Calls between services

| Symptom | Cause | Remedy |
|---|---|---|
| a service cannot reach another one under its public URL, or reaches itself | the host name is not a network alias of the proxy | add it to `ifdd_proxy_internal_hosts` (`cruft update --variables-to-update`), recreate the proxy container |
| `CERTIFICATE_VERIFY_FAILED` or `x509: certificate signed by unknown authority` in a service | the service does not trust the proxy's certificate | copy `certs/ca.crt` into `certs/` of that service, rebuild its image |
| service-to-service HTTPS fails in development only | the self-signed certificate of the development variant | use the production variant |

## Limits

| Symptom | Cause | Remedy |
|---|---|---|
| 429 Too Many Requests | the rate limit of the DoS baseline | check the client addresses in `logs/access.log`; behind Docker's userland proxy all clients may share one bucket |
| 413 on uploads | the body limit of `dos-buffering` on that router | raise `ifdd_proxy_dos_max_request_body_bytes`, or drop `dos-buffering` from the router |
| slow downloads or long responses break off | the write timeout of the entry point | raise `ifdd_proxy_dos_write_timeout` |
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

## Login gate

| Symptom | Cause | Remedy |
|---|---|---|
| oauth2-proxy restarts, log: `x509: certificate signed by unknown authority` | it does not trust the realm's certificate | set `ifdd_proxy_oauth2_proxy_ca_file` (e.g. `ca.crt`) |
| oauth2-proxy does not turn healthy | the realm is not reachable at start | start Traefik, then Keycloak, then the whole project ({ref}`ifdd-proxy-operations`) |
| `/oauth2/` answers 404 on a host without its own `/oauth2/` router | the fallback router is missing while oauth2-proxy is not healthy | wait for the health check; give the service its own `/oauth2/` router |
| login refused: `neither the id_token nor the profileURL set an email` | the user has no e-mail address | set one in Keycloak |
| login refused: `email in id_token ... isn't verified` | the address is not marked as verified | turn "Email verified" on for the user |
| members of the group get 403 | the group claim carries the full path (`/name`) | turn "Full group path" off in the mapper |
| the container fails with a directory where a secret file was expected | `secrets/oauth2_proxy_*` did not exist; Docker mounted empty directories | create the files ({ref}`ifdd-proxy-login-gate`) |
{%- endif %}
