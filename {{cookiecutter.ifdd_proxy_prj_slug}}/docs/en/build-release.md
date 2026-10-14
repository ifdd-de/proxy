(ifdd-proxy-build-release)=
# Build and release

## Images

The proxy builds no image of its own; it runs upstream images with the
configuration of this instance mounted read-only.

| Container | Image | Present |
|---|---|---|
| `proxy` | `traefik:{{ cookiecutter.ifdd_proxy_traefik_version }}` | always |
| `socket-proxy` | `{{ cookiecutter.ifdd_proxy_socket_proxy_image }}` | {{ "yes" if cookiecutter.ifdd_proxy_enable_socket_proxy == "y" else "no (`ifdd_proxy_enable_socket_proxy`)" }} |
| `oauth2-proxy` | `{{ cookiecutter.ifdd_proxy_oauth2_proxy_image }}` | {{ "yes" if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" else "no (`ifdd_proxy_enable_oauth2_proxy`)" }} |

The oauth2-proxy image must be an `-alpine` variant: the health check runs
`wget`, and the default images of oauth2-proxy are distroless. With the
login gate on, the pre-generation hook refuses other images.

```bash
docker compose -f docker-compose-production.yml pull
```

## Versions

The image tags are template variables. To change one in an existing
instance, update it through cruft, so that `.cruft.json` keeps the value:

```bash
cruft update -y --variables-to-update '{"ifdd_proxy_traefik_version": "<tag>"}'
docker compose -f docker-compose-production.yml pull
docker compose -f docker-compose-production.yml up -d
```

The template has been tested with Traefik `v3.7.13`. A new Traefik version
can change behaviour the configuration relies on (router TLS inheritance,
the dashboard with buffering, file provider reloads); check
{ref}`ifdd-proxy-troubleshooting` and the tests below after an update.

## Tests

```bash
pip install -r tests/requirements.txt
pytest -q tests                      # static checks, no Docker needed
tests/smoke.sh development           # starts the container, probes it
tests/smoke.sh production            # own certificates only
```

The static checks read the rendered configuration: the dashboard is never
served without authentication, nothing from `.env` reaches the container,
every mounted host path exists, TLS and `sniStrict` per environment, the DoS
baseline and the buffering placement, the internal host names in both
compose files, the certificate script, the header middlewares and the
oauth2-proxy settings. `tests/smoke.sh` starts the real container and checks
health, the redirect from HTTP to HTTPS and the dashboard login from outside;
it removes every file it created. For Let's Encrypt the production variant
skips itself.

## CI of the instance

`.github/workflows/ci.yml` runs on every push and pull request:

- **Configuration**: the static checks and `docker compose config` for both
  compose files (with the defaults of `dotenv.dist`);
- **Smoke test (development)**: `tests/smoke.sh development`;
- **Template drift**: `cruft check` and `cruft diff`, both informational.
  What `cruft diff` shows either belongs back into the template or on the
  skip list.

## Release

There is no release workflow, because no image is built. A release of the
proxy is a new state of this repository plus `docker compose ... up -d` on
the host.
