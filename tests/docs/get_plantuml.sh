#!/usr/bin/env bash
# Download the pinned PlantUML jar for tests/check_docs.py and print its path.
#
#   export IFDD_PLANTUML_JAR="$(tests/docs/get_plantuml.sh)"
#
# The jar is cached in ${XDG_CACHE_HOME:-$HOME/.cache}/ifdd and its SHA-256
# is checked on every call. Building the diagrams needs Java and Graphviz.
set -euo pipefail

version="1.2026.10"
sha256="e9bc9e6b2eb715e8c0c929f3dcb5fc1923be13f37599b09c293c66d354e88686"
url="https://github.com/plantuml/plantuml/releases/download/v$version/plantuml-$version.jar"
dir="${XDG_CACHE_HOME:-$HOME/.cache}/ifdd"
jar="$dir/plantuml-$version.jar"

check() {
    python3 -c 'import hashlib, sys
h = hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest()
sys.exit(0 if h == sys.argv[2] else f"SHA-256 mismatch for {sys.argv[1]}: {h}")' "$1" "$sha256"
}

if [ ! -f "$jar" ]; then
    mkdir -p "$dir"
    curl -fsSL -o "$jar.part" "$url"
    check "$jar.part"
    mv "$jar.part" "$jar"
fi
check "$jar"
printf '%s\n' "$jar"
