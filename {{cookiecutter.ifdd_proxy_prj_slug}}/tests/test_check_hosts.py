"""Tests of adm_check_hosts.sh with stand-ins for docker, curl and getent.

The script is meant for several servers: some host names are served by this
proxy (network aliases), others, such as the realm, by another server. The
stand-ins answer from a JSON description of such a setup, so every verdict of
the script is checked without Docker, Traefik or a network.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "adm_check_hosts.sh"

pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="no adm_check_hosts.sh (instance without TLS)")

# docker: "compose ... ps -q proxy" prints the container, "inspect" its aliases.
FAKE_DOCKER = """\
#!/usr/bin/env python3
import json, os, sys
setup = json.loads(os.environ["FAKE_SETUP"])
if sys.argv[1:2] == ["compose"]:
    print(setup.get("container", ""))
elif sys.argv[1:2] == ["ps"]:
    print("")
elif sys.argv[1:2] == ["inspect"]:
    print(" ".join(setup["aliases"]) + " ")
"""

# getent hosts NAME: the address from the setup, exit 2 when unknown.
FAKE_GETENT = """\
#!/usr/bin/env python3
import json, os, sys
setup = json.loads(os.environ["FAKE_SETUP"])
address = setup["dns"].get(sys.argv[2])
if address is None:
    sys.exit(2)
print(f"{address}  {sys.argv[2]}")
"""

# curl: answers per host and route ("local" with --connect-to, "remote"
# otherwise): {"exit": n} or {"code": n, "body": "..."}; writes the body to -o
# and the code for -w. Records the arguments of every call.
FAKE_CURL = """\
#!/usr/bin/env python3
import json, os, sys
from urllib.parse import urlsplit
setup = json.loads(os.environ["FAKE_SETUP"])
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
url = args[-1]
host = urlsplit(url).hostname
route = "local" if "--connect-to" in args else "remote"
answer = setup["http"].get(f"{route} {host}", {"exit": 7})
if "exit" in answer:
    sys.exit(answer["exit"])
body = answer.get("body", "ok")
if url.endswith("/.well-known/openid-configuration"):
    body = json.dumps({"issuer": answer["issuer"]})
with open(args[args.index("-o") + 1], "w") as out:
    out.write(body)
sys.stdout.write(str(answer["code"]))
"""

LOCAL = "local"
NO_ROUTER = {"code": 404, "body": "404 page not found\n"}
SERVED = {"code": 200, "body": "ok"}


def internal_hosts():
    match = re.search(r'^INTERNAL_HOSTS="(.*)"$', SCRIPT.read_text(), re.MULTILINE)
    return match[1].split()


def login_gate():
    return re.search(r"^LOGIN_GATE=y$", SCRIPT.read_text(), re.MULTILINE) is not None


def env_value(name):
    match = re.search(rf"^{name}=(.*)$", (ROOT / "dotenv.dist").read_text(), re.MULTILINE)
    return match[1].strip() if match else ""


@pytest.fixture
def run(tmp_path):
    """Copy the instance files the script reads and run it with the stand-ins."""
    work = tmp_path / "instance"
    work.mkdir()
    shutil.copy(SCRIPT, work / SCRIPT.name)
    (work / "certs").mkdir()
    (work / "certs" / "test-ca.pem").write_text("not read by the stand-in\n")
    issuer = "https://id.other-server.example.test/realms/example"
    (work / ".env").write_text(textwrap.dedent(f"""\
        IFDD_PROXY_DASHBOARD_HOST={env_value("IFDD_PROXY_DASHBOARD_HOST")}
        IFDD_PROXY_HTTPS_PORT=443
        IFDD_PROXY_OIDC_ISSUER={issuer}
    """))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, content in (("docker", FAKE_DOCKER), ("getent", FAKE_GETENT), ("curl", FAKE_CURL)):
        path = bin_dir / name
        path.write_text(content)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "curl.log"

    def _run(setup, *args):
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                   FAKE_SETUP=json.dumps(setup), FAKE_LOG=str(log))
        result = subprocess.run(["bash", str(work / SCRIPT.name), "--ca", "certs/test-ca.pem", *args],
                                cwd=work, env=env, capture_output=True, text=True)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    _run.issuer = issuer
    _run.issuer_host = "id.other-server.example.test"
    return _run


def good_setup(run):
    """Every internal host is an alias with a router; the realm is elsewhere."""
    hosts = internal_hosts()
    dashboard = env_value("IFDD_PROXY_DASHBOARD_HOST")
    http = {f"local {h}": SERVED for h in hosts}
    dns = {}
    if dashboard and dashboard not in hosts:
        dns[dashboard] = "192.0.2.10"
        http[f"remote {dashboard}"] = SERVED
    dns[run.issuer_host] = "192.0.2.20"
    http[f"remote {run.issuer_host}"] = {"code": 200, "issuer": run.issuer}
    return {"container": "c0ffee", "aliases": list(hosts), "dns": dns, "http": http}


def lines(result, status):
    return [line for line in result.stdout.splitlines() if line.startswith(status)]


def test_all_hosts_served_and_trusted_pass(run):
    result, _ = run(good_setup(run))
    assert result.returncode == 0, result.stdout + result.stderr
    assert not lines(result, "FAIL")


def test_aliases_are_checked_against_this_proxy_not_dns(run):
    """For an alias the script connects to the local Traefik, as a container would."""
    if not internal_hosts():
        pytest.skip("no internal host names")
    _, calls = run(good_setup(run))
    host = internal_hosts()[0]
    call = next(c for c in calls if c[-1] == f"https://{host}/")
    assert "--connect-to" in call
    assert call[call.index("--connect-to") + 1] == f"{host}:443:127.0.0.1:443"
    assert "--noproxy" in call and call[call.index("--noproxy") + 1] == "*"
    assert call[call.index("--cacert") + 1] == "certs/test-ca.pem"


def test_alias_without_a_router_fails(run):
    """The case of a service on another server whose name is still an alias here."""
    setup = good_setup(run)
    setup["aliases"].append("elsewhere.example.test")
    setup["http"]["local elsewhere.example.test"] = NO_ROUTER
    result, _ = run(setup, "elsewhere.example.test")
    assert result.returncode == 1
    assert any("elsewhere.example.test" in line and "no router" in line for line in lines(result, "FAIL"))


def test_configured_host_that_is_no_alias_asks_for_a_new_container(run):
    hosts = internal_hosts()
    if not hosts:
        pytest.skip("no internal host names")
    setup = good_setup(run)
    setup["aliases"].remove(hosts[0])
    result, _ = run(setup)
    assert result.returncode == 1
    assert any(hosts[0] in line and "recreate the container" in line for line in lines(result, "FAIL"))


def test_host_resolving_to_loopback_fails(run):
    setup = good_setup(run)
    setup["dns"]["loop.example.test"] = "127.0.0.1"
    result, _ = run(setup, "loop.example.test")
    assert result.returncode == 1
    assert any("loop.example.test" in line and "call itself" in line for line in lines(result, "FAIL"))


def test_unresolvable_host_fails(run):
    result, _ = run(good_setup(run), "missing.example.test")
    assert result.returncode == 1
    assert any("missing.example.test" in line and "does not resolve" in line for line in lines(result, "FAIL"))


@pytest.mark.parametrize("exit_code", [60, 51])
def test_untrusted_chain_names_the_missing_intermediate(run, exit_code):
    setup = good_setup(run)
    setup["dns"]["chain.example.test"] = "192.0.2.30"
    setup["http"]["remote chain.example.test"] = {"exit": exit_code}
    result, _ = run(setup, "chain.example.test")
    assert result.returncode == 1
    assert any("chain.example.test" in line and "intermediate CA" in line for line in lines(result, "FAIL"))


def test_issuer_mismatch_fails(run):
    if not login_gate():
        pytest.skip("no login gate in this instance")
    setup = good_setup(run)
    setup["http"][f"remote {run.issuer_host}"] = {"code": 200, "issuer": run.issuer + "-other"}
    result, _ = run(setup)
    assert result.returncode == 1
    assert any("discovery issuer is" in line for line in lines(result, "FAIL"))


def test_no_running_proxy_is_an_error(run):
    setup = good_setup(run)
    setup["container"] = ""
    result, _ = run(setup)
    assert result.returncode == 1
    assert "no single running proxy container" in result.stderr


def test_wrong_usage_exits_2(run):
    result, _ = run(good_setup(run), "--unknown")
    assert result.returncode == 2


def test_script_is_executable_and_parses():
    assert SCRIPT.stat().st_mode & stat.S_IXUSR
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    if shutil.which("shellcheck"):
        subprocess.run(["shellcheck", str(SCRIPT)], check=True)
