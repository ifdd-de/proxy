"""Post-generation setup.

Creates the working copy of the distributed environment file, removes the
files that the chosen options do not use, and keeps secrets, keys and
environment files out of version control.
"""

import base64
import hashlib
import os
import re
import secrets
import shutil
import string

TERMINATOR = "\x1b[0m"
SUCCESS = "\x1b[1;32m [SUCCESS]: "

ENABLE_TLS = "{{ cookiecutter.ifdd_proxy_enable_tls }}" == "y"
ENABLE_LETSENCRYPT = "{{ cookiecutter.ifdd_proxy_enable_letsencrypt }}" == "y"
ENABLE_DOS = "{{ cookiecutter.ifdd_proxy_enable_dos_baseline }}" == "y"
ENABLE_SECURITY_HEADERS = "{{ cookiecutter.ifdd_proxy_enable_security_headers }}" == "y"
ENABLE_OAUTH2_PROXY = "{{ cookiecutter.ifdd_proxy_enable_oauth2_proxy }}" == "y"
DASHBOARD_USER = "{{ cookiecutter.ifdd_proxy_dashboard_user }}"
DASHBOARD_PASSWORD_LENGTH = 32
# Alphabet of the APR1 salt and hash (crypt's base64 variant).
APR1_ALPHABET = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def append_to_gitignore_file(line):
    with open(".gitignore", "a") as gitignore_file:
        gitignore_file.write(line)
        gitignore_file.write(os.linesep)


def remove(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def remove_empty_folders(path_abs):
    for path, _, _ in list(os.walk(path_abs))[::-1]:
        if not os.listdir(path):
            os.rmdir(path)


def create_oauth2_proxy_secrets():
    """Cookie secret generated here; the client secret comes from Keycloak.

    Existing files are kept, so a second run (cruft update renders into a
    temporary directory) never replaces a real value.
    """
    os.makedirs("secrets", exist_ok=True)
    cookie = os.path.join("secrets", "oauth2_proxy_cookie_secret")
    if not os.path.exists(cookie):
        # 32 random bytes, URL-safe base64: the form oauth2-proxy documents
        # for an AES-256 cookie secret.
        with open(cookie, "w") as f:
            f.write(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    client = os.path.join("secrets", "oauth2_proxy_client_secret")
    if not os.path.exists(client):
        with open(client, "w"):
            pass
    for path in (cookie, client):
        # Readable by oauth2-proxy, which runs as a non-root user inside its
        # container; the directory below keeps other host users out.
        os.chmod(path, 0o644)
    os.chmod("secrets", 0o700)


def apr1(password, salt):
    """APR1-MD5 hash as written by `htpasswd -m` and `openssl passwd -apr1`.

    The only htpasswd format Traefik accepts that the standard library can
    compute: bcrypt needs a package, and the crypt module is gone since
    Python 3.13.
    """
    pw, salt_bytes, magic = password.encode(), salt.encode(), b"$apr1$"
    digest = hashlib.md5(pw + salt_bytes + pw).digest()
    data = pw + magic + salt_bytes
    for length in range(len(pw), 0, -16):
        data += digest[: min(16, length)]
    length = len(pw)
    while length:
        data += b"\0" if length & 1 else pw[:1]
        length >>= 1
    digest = hashlib.md5(data).digest()
    for i in range(1000):
        data = pw if i & 1 else digest
        if i % 3:
            data += salt_bytes
        if i % 7:
            data += pw
        data += digest if i & 1 else pw
        digest = hashlib.md5(data).digest()

    def encode(value, count):
        chars = ""
        for _ in range(count):
            chars += APR1_ALPHABET[value & 0x3F]
            value >>= 6
        return chars

    d = digest
    encoded = "".join(
        encode((d[a] << 16) | (d[b] << 8) | d[c], 4)
        for a, b, c in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5))
    ) + encode(d[11], 2)
    return f"$apr1${salt}${encoded}"


def create_dashboard_credentials():
    """Generated password in .env, its APR1 line in secrets/dashboard.htpasswd.

    An existing htpasswd file is kept, like the other secrets.
    """
    os.makedirs("secrets", exist_ok=True)
    htpasswd = os.path.join("secrets", "dashboard.htpasswd")
    if not os.path.exists(htpasswd):
        alphabet = string.ascii_letters + string.digits
        password = "".join(secrets.choice(alphabet) for _ in range(DASHBOARD_PASSWORD_LENGTH))
        salt = "".join(secrets.choice(APR1_ALPHABET) for _ in range(8))
        with open(htpasswd, "w") as f:
            f.write(f"{DASHBOARD_USER}:{apr1(password, salt)}\n")
        # Readable by Traefik in its container; the directory keeps other
        # host users out.
        os.chmod(htpasswd, 0o644)
        with open(".env") as f:
            env = f.read()
        line = "IFDD_PROXY_DASHBOARD_PASSWORD="
        env = re.sub(rf"(?m)^{line}.*$", line + password, env)
        with open(".env", "w") as f:
            f.write(env)
    os.chmod("secrets", 0o700)


def main():
    shutil.copyfile("dotenv.dist", ".env")
    # It holds the dashboard password.
    os.chmod(".env", 0o600)
    append_to_gitignore_file(".env")
    create_dashboard_credentials()

    if not ENABLE_DOS:
        remove("traefik/dynamic/shared/dos.yml")

    if not ENABLE_SECURITY_HEADERS:
        remove("traefik/dynamic/shared/headers.yml")

    if not ENABLE_TLS:
        remove("traefik/dynamic/production/tls.yml")
        remove("traefik/dynamic/development/tls.yml")

    if not ENABLE_TLS or ENABLE_LETSENCRYPT:
        # No own certificates: neither the key directory nor the list of
        # certificates has anything to hold.
        remove("certs")
        remove("traefik/private/certificates.yml.dist")
        remove("adm_01_certs.sh")

    if ENABLE_LETSENCRYPT:
        # Traefik creates acme.json itself, with the restrictive permissions
        # it insists on. Creating the file here would risk getting them wrong.
        os.makedirs("letsencrypt", exist_ok=True)
        with open(os.path.join("letsencrypt", ".gitkeep"), "w"):
            pass

    if ENABLE_OAUTH2_PROXY:
        create_oauth2_proxy_secrets()

    remove_empty_folders(".")
    print(SUCCESS + "Project initialized, keep up the good work!" + TERMINATOR)


if __name__ == "__main__":
    main()
