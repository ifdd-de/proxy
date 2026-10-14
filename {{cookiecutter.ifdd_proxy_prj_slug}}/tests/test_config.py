"""Static checks of the rendered proxy configuration.

These tests read the files as they are in this repository and assert the
invariants the template promises. They need neither Docker nor Traefik, so
they run everywhere; tests/smoke.sh covers the running container.
"""

import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
TRAEFIK = ROOT / "traefik"
COMPOSE_FILES = ["docker-compose-production.yml", "docker-compose-development.yml"]
STATIC_FILES = {
    "docker-compose-production.yml": TRAEFIK / "traefik.yml",
    "docker-compose-development.yml": TRAEFIK / "traefik.development.yml",
}


def load(path):
    return yaml.safe_load(Path(path).read_text())


def proxy_service(compose_file):
    return load(ROOT / compose_file)["services"]["proxy"]


def dos_enabled():
    return (TRAEFIK / "dynamic" / "shared" / "dos.yml").exists()


def letsencrypt_enabled():
    return "certificatesResolvers" in load(TRAEFIK / "traefik.yml")


def tls_enabled():
    return "websecure" in load(TRAEFIK / "traefik.yml")["entryPoints"]


def internal_hosts(compose_file):
    """Aliases of the proxy on the shared network (ifdd_proxy_internal_hosts)."""
    networks = proxy_service(compose_file)["networks"]
    if isinstance(networks, list):
        return []
    return list((networks["proxy"] or {}).get("aliases", []))


CERT_SCRIPT = ROOT / "adm_01_certs.sh"


def oauth2_proxy_service():
    """The oauth2-proxy service of the production file, None without it."""
    return load(ROOT / "docker-compose-production.yml")["services"].get("oauth2-proxy")


# --- every file parses -------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.yml") if ".github" not in p.parts),
)
def test_yaml_parses(path):
    assert load(ROOT / path) is not None


# --- static configuration ----------------------------------------------------

@pytest.mark.parametrize("static", STATIC_FILES.values(), ids=lambda p: p.name)
def test_dashboard_is_never_served_without_authentication(static):
    assert load(static)["api"]["insecure"] is False


@pytest.mark.parametrize("static", STATIC_FILES.values(), ids=lambda p: p.name)
def test_ping_listens_on_loopback_only(static):
    config = load(static)
    assert config["ping"]["entryPoint"] == "ping"
    assert config["entryPoints"]["ping"]["address"].startswith("127.0.0.1:")


@pytest.mark.parametrize("static", STATIC_FILES.values(), ids=lambda p: p.name)
def test_every_entry_point_sets_alias_headers_strategy(static):
    # Without it Traefik warns at startup and forwards aliasing header names.
    for name, entry_point in load(static)["entryPoints"].items():
        assert entry_point.get("http", {}).get("aliasHeadersStrategy") in ("delete", "reject", "keep"), name


@pytest.mark.parametrize("static", STATIC_FILES.values(), ids=lambda p: p.name)
def test_containers_are_not_exposed_by_default(static):
    assert load(static)["providers"]["docker"]["exposedByDefault"] is False


def test_development_never_uses_lets_encrypt():
    config = load(TRAEFIK / "traefik.development.yml")
    assert "certificatesResolvers" not in config
    websecure = config["entryPoints"].get("websecure", {})
    assert "certResolver" not in (websecure.get("http", {}).get("tls") or {})


def test_lets_encrypt_resolver_is_set_on_the_entry_point():
    config = load(TRAEFIK / "traefik.yml")
    if "certificatesResolvers" not in config:
        pytest.skip("Let's Encrypt not enabled")
    assert config["entryPoints"]["websecure"]["http"]["tls"]["certResolver"] == "letsencrypt"
    assert config["certificatesResolvers"]["letsencrypt"]["acme"]["httpChallenge"]["entryPoint"] == "web"


# --- DoS baseline ------------------------------------------------------------

@pytest.mark.parametrize("static", STATIC_FILES.values(), ids=lambda p: p.name)
def test_dos_baseline_is_attached_exactly_when_it_exists(static):
    attached = [
        name
        for name, entry_point in load(static)["entryPoints"].items()
        if "dos-baseline@file" in entry_point.get("http", {}).get("middlewares", [])
    ]
    if dos_enabled():
        assert attached, "dos.yml exists but no entry point uses dos-baseline@file"
    else:
        assert not attached, "an entry point references dos-baseline@file, but dos.yml was removed"


def test_buffering_stays_out_of_the_entry_point_chain():
    # Attached to the entry point, buffering also wraps api@internal and every
    # dashboard request fails (observed with Traefik v3.7.13).
    if not dos_enabled():
        pytest.skip("DoS baseline not enabled")
    middlewares = load(TRAEFIK / "dynamic" / "shared" / "dos.yml")["http"]["middlewares"]
    assert "dos-buffering" not in middlewares["dos-baseline"]["chain"]["middlewares"]


# --- TLS ---------------------------------------------------------------------

def test_sni_strict_in_production_and_relaxed_in_development():
    if not tls_enabled():
        pytest.skip("TLS not enabled")
    production = load(TRAEFIK / "dynamic" / "production" / "tls.yml")
    development = load(TRAEFIK / "dynamic" / "development" / "tls.yml")
    assert production["tls"]["options"]["default"]["sniStrict"] is True
    # Traefik's self-signed default certificate matches no host name.
    assert development["tls"]["options"]["default"]["sniStrict"] is False


def test_default_certificate_is_also_in_the_certificate_list():
    # With sniStrict on, a certificate that is only the store default matches
    # no server name, and every handshake fails (observed with v3.7.13).
    if not tls_enabled() or letsencrypt_enabled():
        pytest.skip("no own certificates")
    tls = load(TRAEFIK / "dynamic" / "production" / "tls.yml")["tls"]
    default = tls["stores"]["default"]["defaultCertificate"]
    assert default in tls["certificates"]


# --- compose -----------------------------------------------------------------

@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_nothing_from_dotenv_reaches_the_container(compose_file):
    # Traefik reads TRAEFIK_* variables as configuration.
    service = proxy_service(compose_file)
    assert "env_file" not in service
    assert "environment" not in service


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_configuration_comes_from_the_static_file_only(compose_file):
    assert proxy_service(compose_file)["command"] == ["--configFile=/etc/traefik/traefik.yml"]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_the_static_file_matching_the_compose_file_is_mounted(compose_file):
    expected = "./traefik/" + STATIC_FILES[compose_file].name + ":/etc/traefik/traefik.yml:ro"
    assert expected in proxy_service(compose_file)["volumes"]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_dashboard_router_is_authenticated_and_inherits_tls(compose_file):
    labels = proxy_service(compose_file)["labels"]
    assert "traefik.http.routers.dashboard.middlewares=dashboard-auth@file" in labels
    # A router tls section would replace the entry point TLS configuration,
    # including the Let's Encrypt resolver.
    assert not [label for label in labels if ".tls" in label]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_every_mounted_host_path_exists(compose_file):
    for volume in proxy_service(compose_file)["volumes"]:
        source = volume.split(":")[0]
        if source.startswith("./"):
            assert (ROOT / source).exists(), f"{compose_file} mounts {source}, which does not exist"


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_shared_network_is_external(compose_file):
    # Owned by no project: otherwise compose warns when it already exists and
    # a down of the owning project tries to remove it under running services.
    network = load(ROOT / compose_file)["networks"]["proxy"]
    assert network.get("external") is True


def test_lets_encrypt_storage_is_mounted_exactly_when_enabled():
    volumes = proxy_service("docker-compose-production.yml")["volumes"]
    mounted = any(volume.startswith("./letsencrypt:") for volume in volumes)
    assert mounted == letsencrypt_enabled()


def test_dotenv_holds_no_traefik_variables():
    for line in (ROOT / "dotenv.dist").read_text().splitlines():
        if line and not line.startswith("#"):
            assert line.startswith("IFDD_PROXY_"), line


def test_secrets_and_keys_are_git_ignored():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    for pattern in (".env", "certs/*", "secrets/*", "letsencrypt/*"):
        assert pattern in ignored


# --- internal host names -------------------------------------------------------

def test_internal_hosts_are_the_same_in_both_compose_files():
    assert internal_hosts("docker-compose-production.yml") == internal_hosts("docker-compose-development.yml")


def test_cert_script_exists_exactly_with_own_certificates():
    assert CERT_SCRIPT.exists() == (tls_enabled() and not letsencrypt_enabled())


def test_cert_script_covers_the_internal_hosts():
    if not CERT_SCRIPT.exists():
        pytest.skip("no own certificates")
    match = re.search(r'^INTERNAL_HOSTS="(.*)"$', CERT_SCRIPT.read_text(), re.MULTILINE)
    assert match, "INTERNAL_HOSTS line not found"
    assert match.group(1).split() == internal_hosts("docker-compose-production.yml")


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")
def test_cert_script_creates_a_chain_and_never_overwrites(tmp_path):
    if not CERT_SCRIPT.exists():
        pytest.skip("no own certificates")
    shutil.copy(CERT_SCRIPT, tmp_path / CERT_SCRIPT.name)
    (tmp_path / ".env").write_text("IFDD_PROXY_DASHBOARD_HOST=dashboard.test\n")
    tls = load(TRAEFIK / "dynamic" / "production" / "tls.yml")["tls"]["stores"]["default"]["defaultCertificate"]
    cert = tmp_path / tls["certFile"].removeprefix("/")
    key = tmp_path / tls["keyFile"].removeprefix("/")
    ca = tmp_path / "certs" / "ca.crt"

    subprocess.run(["bash", CERT_SCRIPT.name], cwd=tmp_path, check=True, capture_output=True)

    subprocess.run(["openssl", "verify", "-CAfile", ca, cert], check=True, capture_output=True)
    text = subprocess.run(["openssl", "x509", "-in", cert, "-noout", "-text"],
                          check=True, capture_output=True, text=True).stdout
    for host in internal_hosts("docker-compose-production.yml") + ["dashboard.test"]:
        assert f"DNS:{host}" in text
    for private in (key, tmp_path / "certs" / "ca.key"):
        assert stat.S_IMODE(private.stat().st_mode) == 0o600

    before = cert.read_bytes()
    second = subprocess.run(["bash", CERT_SCRIPT.name], cwd=tmp_path, capture_output=True, text=True)
    assert second.returncode != 0
    assert cert.read_bytes() == before


# --- security headers ----------------------------------------------------------

def security_headers_enabled():
    return (TRAEFIK / "dynamic" / "shared" / "headers.yml").exists()


def test_headers_file_tracks_the_switch():
    # Rendered only when ifdd_proxy_enable_security_headers is y; removed by the
    # post-gen hook otherwise. dashboard.yml is always present, so the shared
    # directory exists either way.
    expected = {"security-headers"} <= set(
        load(TRAEFIK / "dynamic" / "shared" / "headers.yml")["http"]["middlewares"]
    ) if security_headers_enabled() else True
    assert expected


def test_header_middlewares_are_defined():
    if not security_headers_enabled():
        pytest.skip("security headers off")
    mids = load(TRAEFIK / "dynamic" / "shared" / "headers.yml")["http"]["middlewares"]
    assert "security-headers" in mids
    for name in ("csp-api", "csp-api-docs", "csp-ui"):
        assert name in mids, name
    h = mids["security-headers"]["headers"]
    assert h["contentTypeNosniff"] is True
    assert h["customFrameOptionsValue"]
    # the Server header is emptied (removed)
    assert h["customResponseHeaders"]["Server"] == ""


def test_every_csp_forbids_framing():
    if not security_headers_enabled():
        pytest.skip("security headers off")
    mids = load(TRAEFIK / "dynamic" / "shared" / "headers.yml")["http"]["middlewares"]
    for name in ("csp-api", "csp-api-docs", "csp-ui"):
        assert "frame-ancestors 'none'" in mids[name]["headers"]["contentSecurityPolicy"]


# --- oauth2-proxy: trust in the realm's certificate --------------------------

def test_oauth2_proxy_trusts_a_ca_exactly_when_it_mounts_one():
    """PROVIDER_CA_FILES and the mount of that one file come together.

    Without the CA of a local certificate authority oauth2-proxy stops at
    start (x509: certificate signed by unknown authority).
    """
    service = oauth2_proxy_service()
    if service is None:
        pytest.skip("no oauth2-proxy in this instance")
    env = service["environment"]
    ca_file = env.get("OAUTH2_PROXY_PROVIDER_CA_FILES")
    cert_mounts = [v for v in service["volumes"] if isinstance(v, dict) and v["target"].startswith("/certs/")]
    if ca_file is None:
        assert cert_mounts == []
        assert "OAUTH2_PROXY_USE_SYSTEM_TRUST_STORE" not in env
        return
    assert env["OAUTH2_PROXY_USE_SYSTEM_TRUST_STORE"] == "true"
    [mount] = cert_mounts
    assert mount["type"] == "bind"
    assert mount["target"] == ca_file
    assert mount["source"] == "./certs/" + Path(ca_file).name
    assert mount["read_only"] is True
    assert mount["bind"]["create_host_path"] is False


def test_oauth2_proxy_has_a_health_check_its_image_can_run():
    """wget on /ready; only the -alpine images have wget (the default ones are distroless)."""
    service = oauth2_proxy_service()
    if service is None:
        pytest.skip("no oauth2-proxy in this instance")
    assert service["image"].endswith("-alpine")
    test = service["healthcheck"]["test"]
    assert test[:2] == ["CMD", "wget"] and test[-1] == "http://127.0.0.1:4180/ready"
    assert service["environment"]["OAUTH2_PROXY_HTTP_ADDRESS"].endswith(":4180")


def test_oauth2_proxy_never_sees_the_private_keys():
    service = oauth2_proxy_service()
    if service is None:
        pytest.skip("no oauth2-proxy in this instance")
    for volume in service["volumes"]:
        source = volume["source"] if isinstance(volume, dict) else volume.split(":")[0]
        assert source.rstrip("/") not in ("./certs", "certs"), f"oauth2-proxy mounts {source}"
        assert not source.endswith(".key"), f"oauth2-proxy mounts {source}"
