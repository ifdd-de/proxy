# Secrets

Git-ignored except for this file. Mounted read-only at
`/etc/traefik/secrets`.

## dashboard.htpasswd

Users for the dashboard (`/dashboard/`, `/api`). One `user:hash` per line.

Generating the instance created it with one user,
`{{ cookiecutter.ifdd_proxy_dashboard_user }}`, and a random password; both are in `.env`
(`IFDD_PROXY_DASHBOARD_USER`, `IFDD_PROXY_DASHBOARD_PASSWORD`), for reading
only: Traefik checks this file. The generated hash is APR1-MD5, the strongest
format Traefik accepts that the standard library of Python can compute.

To change the password, or for an instance generated before this existed,
write the file yourself, preferably with bcrypt, and update `.env` to match:

```bash
htpasswd -nB {{ cookiecutter.ifdd_proxy_dashboard_user }} > secrets/dashboard.htpasswd
```

Traefik reads this file only at startup. After creating or changing it,
restart the proxy (`docker compose -f docker-compose-production.yml restart proxy`);
until then the old users and passwords stay valid and new ones are refused.

The dashboard is at `https://<dashboard host>/dashboard/`, with the trailing
slash; `/dashboard` answers 404. If a browser keeps asking for the password
although `curl -u <user> https://<dashboard host>/dashboard/` succeeds, it is
probably still sending old credentials: try a private window, or restart the
browser.

`-C <cost>` raises the bcrypt cost (the `htpasswd` default is low). Higher
costs slow down every dashboard request, because basic authentication checks
the password on each one. Check the option against your `htpasswd` version.

Without this file the dashboard answers 404: Traefik cannot build the
authentication middleware and unmounts the router that uses it.
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}

## oauth2_proxy_cookie_secret, oauth2_proxy_client_secret

`oauth2_proxy_cookie_secret` is generated (32 random bytes, URL-safe
base64); replacing it signs everybody out. Put the secret of the Keycloak
client `IFDD_PROXY_OIDC_CLIENT_ID` into `oauth2_proxy_client_secret`
(no trailing newline: `printf '%s' '<secret>' > secrets/oauth2_proxy_client_secret`).
Both are mounted read-only into the oauth2-proxy container.
{%- endif %}
