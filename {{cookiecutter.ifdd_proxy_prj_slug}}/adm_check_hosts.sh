#!/usr/bin/env bash
# Checks, read-only, how the host names of this server reach their services.
# Meant for setups with several servers, where some services run here and
# others (e.g. Keycloak) on another server.
#
#   ./adm_check_hosts.sh [--ca FILE] [--container ID] [HOST ...]
#
# Checked by default: the internal host names of this instance
# (ifdd_proxy_internal_hosts), the dashboard host from .env and, with the login
# gate, the host of the realm; further hosts as arguments.
#
# For every host:
#   - Is it a network alias of this proxy on the shared network? Containers on
#     that network then reach the local Traefik for it; otherwise they ask
#     DNS like the host does.
#   - Alias: this Traefik must have a router for it. Its own "404 page not
#     found" means it has none; containers calling the host get that 404
#     instead of the service on the other server.
#   - No alias: DNS must answer, and not with a loopback address (a container
#     would call itself).
#   - TLS against the CA file (--ca; default: the CA file of the login gate,
#     else the system store): the served chain must lead to that CA, so it
#     must contain intermediate CAs, and the name must be in the certificate.
# With the login gate, the issuer of the realm's discovery document must equal
# IFDD_PROXY_OIDC_ISSUER.
#
# Changes nothing, reads no secrets. Needs bash, curl, getent and access to
# the Docker daemon; the proxy must be running. Exit code 0 when nothing
# failed, 1 when a check failed, 2 on wrong usage.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

INTERNAL_HOSTS="{{ cookiecutter.ifdd_proxy_internal_hosts.split(",") | map("trim") | reject("equalto", "") | join(" ") }}"
NETWORK="{{ cookiecutter.ifdd_proxy_network }}"
{%- if cookiecutter.ifdd_proxy_enable_oauth2_proxy == "y" %}
LOGIN_GATE=y
DEFAULT_CA="{% if cookiecutter.ifdd_proxy_oauth2_proxy_ca_file %}certs/{{ cookiecutter.ifdd_proxy_oauth2_proxy_ca_file }}{% endif %}"
{%- else %}
LOGIN_GATE=n
DEFAULT_CA=""
{%- endif %}
{% raw %}
COMPOSE_FILE=docker-compose-production.yml
# Body of Traefik's answer when no router matches the request.
NO_ROUTER_BODY="404 page not found"

usage() { echo "usage: $0 [--ca FILE] [--container ID] [HOST ...]" >&2; exit 2; }

ca_file=""
container=""
extra_hosts=()
while (($# > 0)); do
    case $1 in
        --ca) (($# >= 2)) || usage; ca_file=$2; shift 2 ;;
        --container) (($# >= 2)) || usage; container=$2; shift 2 ;;
        -h|--help) usage ;;
        -*) usage ;;
        *) extra_hosts+=("$1"); shift ;;
    esac
done
if [[ -z $ca_file && -n $DEFAULT_CA && -f $DEFAULT_CA ]]; then
    ca_file=$DEFAULT_CA
fi
if [[ -n $ca_file && ! -r $ca_file ]]; then
    echo "ERROR: CA file $ca_file is not readable" >&2
    exit 2
fi

failures=0
report() {  # STATUS HOST MESSAGE
    printf '%-4s  %s  %s\n' "$1" "$2" "$3"
    if [[ $1 == FAIL ]]; then failures=$((failures + 1)); fi
}

# Values from .env (no secrets are read): dashboard host, HTTPS port, issuer.
env_value() {
    [[ -f .env ]] || return 0
    sed -n "s/^$1=//p" .env | tail -1 | tr -d "\"'"
}
dashboard_host=$(env_value IFDD_PROXY_DASHBOARD_HOST)
https_port=$(env_value IFDD_PROXY_HTTPS_PORT)
https_port=${https_port:-443}
issuer=""
issuer_host=""
if [[ $LOGIN_GATE == y ]]; then
    issuer=$(env_value IFDD_PROXY_OIDC_ISSUER)
    issuer_host=${issuer#*://}
    issuer_host=${issuer_host%%/*}
    issuer_host=${issuer_host%%:*}
fi

# The running proxy container and its aliases on the shared network.
if [[ -z $container ]]; then
    container=$(docker compose -f "$COMPOSE_FILE" ps -q proxy 2>/dev/null || true)
fi
if [[ -z $container ]]; then
    # Started with another project name (e.g. docker compose -f <dir>/...):
    # find it by the labels Compose sets.
    container=$(docker ps -q --filter label=com.docker.compose.service=proxy \
        --filter "label=com.docker.compose.project.working_dir=$PWD" 2>/dev/null || true)
fi
if [[ -z $container || $container == *$'\n'* ]]; then
    echo "ERROR: no single running proxy container found; start the proxy or pass --container" >&2
    exit 1
fi
aliases=" $(docker inspect --format "{{with index .NetworkSettings.Networks \"$NETWORK\"}}{{range .Aliases}}{{.}} {{end}}{{end}}" "$container") "

# Hosts to check, without duplicates, in the order given.
hosts=()
for host in $INTERNAL_HOSTS $dashboard_host $issuer_host "${extra_hosts[@]+"${extra_hosts[@]}"}"; do
    case " ${hosts[*]} " in *" $host "*) ;; *) hosts+=("$host") ;; esac
done

# A configured internal host that is no alias: the container was created
# with an older list; recreate it (docker compose up -d) to apply the list.
for host in $INTERNAL_HOSTS; do
    if [[ $aliases != *" $host "* ]]; then
        report FAIL "$host" "in ifdd_proxy_internal_hosts, but no alias of the running proxy on $NETWORK: recreate the container"
    fi
done

ca_opt=()
if [[ -n $ca_file ]]; then
    ca_opt=(--cacert "$ca_file")
fi
tmp_body=$(mktemp)
trap 'rm -f "$tmp_body"' EXIT

curl_error() {  # CURL_EXIT_CODE
    case $1 in
        6) echo "name not resolved" ;;
        7) echo "connection refused or no route" ;;
        28) echo "timeout" ;;
        35) echo "TLS handshake failed" ;;
        51|60) echo "certificate not trusted: chain incomplete (intermediate CA not served) or another CA than ${ca_file:-the system store}" ;;
        *) echo "curl exit code $1" ;;
    esac
}

fetch() {  # URL [curl options...] -> sets code, rc; body in $tmp_body
    local url=$1; shift
    rc=0
    # --noproxy: containers call the services directly, so does this check,
    # whatever HTTPS_PROXY or NO_PROXY say on this host.
    code=$(curl -sS --noproxy '*' --max-time 10 -o "$tmp_body" -w '%{http_code}' \
        "${ca_opt[@]+"${ca_opt[@]}"}" "$@" "$url" 2>/dev/null) || rc=$?
}

for host in "${hosts[@]+"${hosts[@]}"}"; do
    if [[ $aliases == *" $host "* ]]; then
        # Containers reach the local Traefik for this name.
        fetch "https://$host/" --connect-to "$host:443:127.0.0.1:$https_port"
        if ((rc != 0)); then
            report FAIL "$host" "alias of this proxy; TLS on this proxy: $(curl_error "$rc")"
        elif [[ $code == 404 && $(head -c 64 "$tmp_body") == "$NO_ROUTER_BODY"* ]]; then
            report FAIL "$host" "alias of this proxy, but this proxy has no router for it: remove it from ifdd_proxy_internal_hosts if the service runs on another server"
        else
            report OK "$host" "alias of this proxy, served here (HTTP $code), TLS trusted"
        fi
    else
        address=$(getent hosts "$host" | awk '{print $1; exit}' || true)
        if [[ -z $address ]]; then
            report FAIL "$host" "no alias of this proxy and DNS does not resolve it"
            continue
        fi
        case $address in
            127.*|::1)
                report FAIL "$host" "no alias of this proxy and DNS answers $address: a container would call itself; add it to ifdd_proxy_internal_hosts if it runs here"
                continue ;;
        esac
        fetch "https://$host/"
        if ((rc != 0)); then
            report FAIL "$host" "resolves to $address; $(curl_error "$rc")"
        elif [[ $code == 404 && $(head -c 64 "$tmp_body") == "$NO_ROUTER_BODY"* ]]; then
            report WARN "$host" "resolves to $address, but the proxy there has no router for it"
        else
            report OK "$host" "resolves to $address (HTTP $code), TLS trusted"
        fi
    fi
done

if [[ -n $issuer ]]; then
    discovery="$issuer/.well-known/openid-configuration"
    if [[ $aliases == *" $issuer_host "* ]]; then
        fetch "$discovery" --connect-to "$issuer_host:443:127.0.0.1:$https_port"
    else
        fetch "$discovery"
    fi
    if ((rc != 0)); then
        report FAIL "$issuer_host" "discovery of $issuer: $(curl_error "$rc")"
    elif [[ $code != 200 ]]; then
        report FAIL "$issuer_host" "discovery of $issuer answers HTTP $code"
    else
        found=$(grep -o '"issuer" *: *"[^"]*"' "$tmp_body" | head -1 | sed 's/.*: *"//; s/"$//')
        if [[ $found == "$issuer" ]]; then
            report OK "$issuer_host" "discovery issuer matches IFDD_PROXY_OIDC_ISSUER"
        else
            report FAIL "$issuer_host" "discovery issuer is '$found', IFDD_PROXY_OIDC_ISSUER is '$issuer'"
        fi
    fi
fi

if ((failures > 0)); then
    echo "$failures check(s) failed"
    exit 1
fi
echo "all checks passed"
{% endraw %}
