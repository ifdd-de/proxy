#!/usr/bin/env bash
# Creates a local certificate authority and, signed by it, the default
# certificate of this proxy. Meant for hosts without certificates of their own,
# such as test machines with short host names. Whoever has real certificates
# puts them into certs/ instead and never runs this script.
#
#   ./adm_01_certs.sh
#
# Writes, and refuses to start if any of them already exists:
#
#   certs/ca.crt    CA certificate: trust it in browsers or the operating
#                   system, and copy it into certs/ of every service that
#                   calls another one through this proxy (e.g. be)
#   certs/ca.key    CA private key
#   certs/{{ cookiecutter.ifdd_proxy_default_cert_file }}, certs/{{ cookiecutter.ifdd_proxy_default_key_file }}
#                   default certificate, signed by the CA, and its key
#
# The certificate covers the host names in INTERNAL_HOSTS
# (ifdd_proxy_internal_hosts) and the dashboard host from .env. To cover a
# different set of names, delete the four files and run the script again.
# Needs openssl.
set -euo pipefail
cd "$(dirname "$0")"

INTERNAL_HOSTS="{{ cookiecutter.ifdd_proxy_internal_hosts.split(",") | map("trim") | reject("equalto", "") | join(" ") }}"
CERT=certs/{{ cookiecutter.ifdd_proxy_default_cert_file }}
KEY=certs/{{ cookiecutter.ifdd_proxy_default_key_file }}
CA_CERT=certs/ca.crt
CA_KEY=certs/ca.key
CA_DAYS=3650
# 825 days: the longest validity Apple platforms accept for TLS server
# certificates, also from a locally trusted CA.
CERT_DAYS=825

die() { echo "ERROR: $*" >&2; exit 1; }

command -v openssl >/dev/null || die "openssl not found"
[ -f .env ] || die ".env not found (it holds IFDD_PROXY_DASHBOARD_HOST)"

for file in "$CA_CERT" "$CA_KEY" "$CERT" "$KEY"; do
  [ -e "$file" ] && die "$file exists; nothing was changed. Delete all four files to start over."
done

DASHBOARD_HOST=$(sed -n 's/^IFDD_PROXY_DASHBOARD_HOST=//p' .env | tail -1 | tr -d "\"'")

# Host names, without duplicates, in the order given.
HOSTS=""
for host in $INTERNAL_HOSTS $DASHBOARD_HOST; do
  case " $HOSTS " in *" $host "*) ;; *) HOSTS="$HOSTS $host" ;; esac
done
HOSTS=${HOSTS# }
[ -n "$HOSTS" ] || die "no host names: set ifdd_proxy_internal_hosts or IFDD_PROXY_DASHBOARD_HOST"
FIRST_HOST=${HOSTS%% *}
SAN="DNS:$(echo "$HOSTS" | sed 's/ /,DNS:/g')"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Private keys are created readable by the owner only.
umask 077
mkdir -p certs

cat > "$WORK/ca.cnf" <<EOF
[req]
distinguished_name = dn
prompt = no
[dn]
CN = IFDD local CA ($(hostname))
[ca]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
EOF

cat > "$WORK/server.ext" <<EOF
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = $SAN
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
EOF

# EC P-256 keys; the CA signs with SHA-256.
openssl ecparam -name prime256v1 -genkey -noout -out "$WORK/ca.key"
openssl req -new -x509 -sha256 -days "$CA_DAYS" -key "$WORK/ca.key" \
  -config "$WORK/ca.cnf" -extensions ca -out "$WORK/ca.crt"

openssl ecparam -name prime256v1 -genkey -noout -out "$WORK/server.key"
openssl req -new -sha256 -key "$WORK/server.key" -subj "/CN=$FIRST_HOST" -out "$WORK/server.csr"
openssl x509 -req -sha256 -days "$CERT_DAYS" -in "$WORK/server.csr" \
  -CA "$WORK/ca.crt" -CAkey "$WORK/ca.key" -CAcreateserial \
  -extfile "$WORK/server.ext" -out "$WORK/server.crt" 2>/dev/null

openssl verify -CAfile "$WORK/ca.crt" "$WORK/server.crt" >/dev/null \
  || die "the new certificate does not verify against the new CA"

# Certificates are public; Traefik and the services only need to read them.
chmod 0644 "$WORK/ca.crt" "$WORK/server.crt"
mv "$WORK/ca.key" "$CA_KEY"
mv "$WORK/ca.crt" "$CA_CERT"
mv "$WORK/server.key" "$KEY"
mv "$WORK/server.crt" "$CERT"

echo "Created $CA_CERT, $CA_KEY, $CERT and $KEY for: $HOSTS"
echo "Next: restart the proxy, trust $CA_CERT in your browser or operating system,"
echo "and copy it into the certs/ directory of the services that call others (e.g. be)."
