(ifdd-proxy-operations)=
# Operations
{%- set tls = cookiecutter.ifdd_proxy_enable_tls == "y" %}
{%- set le = cookiecutter.ifdd_proxy_enable_letsencrypt == "y" %}
{%- set own = tls and not le %}
{%- set dos = cookiecutter.ifdd_proxy_enable_dos_baseline == "y" %}
{%- set o2 = cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

## Start, stop, order

```bash
docker compose -f docker-compose-production.yml up -d
docker compose -f docker-compose-production.yml ps
docker compose -f docker-compose-production.yml down     # the network stays
```

The proxy comes first on a node: every other service joins its network and
reaches Keycloak and the schema service through it.
{%- if o2 %}
oauth2-proxy needs a reachable realm at start, and Keycloak is itself behind
Traefik. Start Traefik alone, then Keycloak, then the whole project:

```bash
docker compose -f docker-compose-production.yml up -d --wait proxy
# start the Keycloak instance and wait until it is healthy
docker compose -f docker-compose-production.yml up -d --wait
```
{%- endif %}

`.adm_03_up_services.sh` of the meta repository starts all services in this
order.

## Health checks

| Container | Check | Interval |
|---|---|---|
| `proxy` | `traefik healthcheck` against the ping entry point (`127.0.0.1:8082`, loopback only) | 30 s, timeout 5 s, 3 retries, start period 10 s |
{%- if o2 %}
| `oauth2-proxy` | `wget` on `http://127.0.0.1:4180/ready` | 15 s, timeout 5 s, 5 retries, start period 30 s |
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
| `socket-proxy` | none | |
{%- endif %}

Traefik ignores containers that are not healthy (yet): their routers are
missing until the health check passes.

## Applying changes

The static configuration (`traefik/traefik.yml`) always needs a restart. The
file provider watches `/etc/traefik/dynamic`, but in tests with v3.7.13 only
changes directly in that directory triggered a reload, not changes in its
subdirectories, where all mounts are. So after any change of the
configuration, of `secrets/dashboard.htpasswd` or of the files in `certs/`:

```bash
docker compose -f docker-compose-production.yml restart proxy
```

Labels of the services are read from the Docker API and take effect when the
service container is recreated; the proxy needs no restart for them.

## Logs

```bash
docker compose -f docker-compose-production.yml logs -f proxy
tail -f logs/access.log
```

The level of the Traefik log is `{{ cookiecutter.ifdd_proxy_log_level }}`
(`ifdd_proxy_log_level`). The access log goes to `logs/access.log` and is
written in batches of up to 500 lines (`bufferingSize`), so the newest
requests may appear late. The template configures no rotation of the access
log; `logs/` grows until it is rotated or emptied.

At start Traefik v3.7.13 logs one warning that it can reject some encoded
characters in request paths; it is expected.

## Resources

| Container | Limit | Restart |
|---|---|---|
| `proxy` | memory `{{ cookiecutter.ifdd_proxy_memory_limit }}` (`ifdd_proxy_memory_limit`) | `always` |
{%- if o2 %}
| `oauth2-proxy` | memory `128M` | `always` |
{%- endif %}
{%- if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" %}
| `socket-proxy` | none | `always` |
{%- endif %}

The development variant restarts with `unless-stopped` and has no memory
limit.

```{note}
Not tested: whether the memory limit fits real traffic. It is the template
default, not a measured value.
```

## DoS baseline
{%- if dos %}

Attached to the public entry point: a rate limit (`dos-ratelimit`, answers
429) and a limit of concurrent requests (`dos-inflight`), both per source
address, plus limits on header size, HTTP/2 streams and timeouts.

| Setting | Here |
|---|---|
| requests per period (average, refill) | {{ cookiecutter.ifdd_proxy_dos_rate_average }} per {{ cookiecutter.ifdd_proxy_dos_rate_period }} |
| burst | {{ cookiecutter.ifdd_proxy_dos_rate_burst }} |
| concurrent requests per source | {{ cookiecutter.ifdd_proxy_dos_inflight_amount }} |
| IPv6 sources grouped by prefix | /{{ cookiecutter.ifdd_proxy_dos_ipv6_subnet }} |
| maximum header size | {{ cookiecutter.ifdd_proxy_dos_max_header_bytes }} bytes |
| HTTP/2 streams per connection | {{ cookiecutter.ifdd_proxy_dos_h2_max_streams }} |
| read, write, idle timeout | {{ cookiecutter.ifdd_proxy_dos_read_timeout }}, {{ cookiecutter.ifdd_proxy_dos_write_timeout }}, {{ cookiecutter.ifdd_proxy_dos_idle_timeout }} |
{%- if cookiecutter.ifdd_proxy_dos_enable_buffering == "y" %}
| request body, opt-in per router (`dos-buffering`) | {{ cookiecutter.ifdd_proxy_dos_max_request_body_bytes }} bytes, {{ cookiecutter.ifdd_proxy_dos_mem_request_body_bytes }} of them in memory |
{%- endif %}

**The values are syntax examples, not recommendations.** They have not been
measured against any workload. Derive them from load tests of the services
behind this proxy, and bear in mind that the write timeout also cuts off slow
downloads and long-running responses.

Source address:

- Without a trusted proxy in front (`ifdd_proxy_trusted_ips` empty) the
  limits use the address of the TCP connection. `X-Forwarded-For` is ignored
  for this and is removed from untrusted requests before they reach a
  service.
- With a trusted proxy in front the limits use the right-most
  `X-Forwarded-For` entry. Clients that bypass that proxy arrive without the
  header and share one bucket; they cannot open new ones by forging it.
- Unverified: with Docker's userland proxy (the default for published ports,
  in particular over IPv6) Traefik may see the Docker gateway instead of the
  client. All clients then share one bucket. Check the client addresses in
  `logs/access.log` before relying on the limits.
{%- else %}

Off in this instance (`ifdd_proxy_enable_dos_baseline`): no rate limit, no
limit of concurrent requests, no entry point limits beyond Traefik's
defaults.
{%- endif %}

## Certificates
{%- if own %}

`adm_01_certs.sh` issues the CA for 3650 days and the default certificate for
825 days (the longest validity Apple platforms accept for TLS server
certificates). Check the expiry date:

```bash
openssl x509 -in certs/{{ cookiecutter.ifdd_proxy_default_cert_file }} -noout -enddate
```

The script does not renew: it refuses to run while any of its four files
exists. Starting over creates a new CA, which every browser, operating system
and service image that trusted the old one must receive again. Certificates
of your own are renewed outside this instance; replace the files and restart
the proxy. A new host name in the certificate needs the same steps.
{%- elif le %}

Traefik renews the certificates from Let's Encrypt itself and keeps them in
`letsencrypt/acme.json`. Do not delete that file: it holds the ACME account
and the certificates, and requesting all of them again counts against the
rate limits of Let's Encrypt.

```{note}
Not tested: issuance and renewal by Let's Encrypt (no access to the ACME
servers while the template was built).
```
{%- else %}

None: TLS is off in this instance.
{%- endif %}

## Backup

| Path | Content |
|---|---|
| `.env` | dashboard host, host ports, dashboard login{% if o2 %}, realm and client of oauth2-proxy{% endif %} |
| `secrets/` | `dashboard.htpasswd`{% if o2 %}, cookie and client secret of oauth2-proxy{% endif %} |
{%- if own %}
| `certs/` | certificates and keys, including the CA key `ca.key` if `adm_01_certs.sh` created it |
{%- elif le %}
| `letsencrypt/acme.json` | ACME account and certificates with their keys |
{%- endif %}
| `traefik/private/` | instance-specific dynamic configuration |

Everything else comes from the template and Git. The paths above hold
secrets and private keys: keep the backup as protected as the host.

```{note}
Not tested: a restore of these files on another host.
```

## Updates

New template states arrive with `cruft update`; the skip list keeps the
paths above untouched. Image versions: see {ref}`ifdd-proxy-build-release`.
After every update run the tests and restart the proxy.
