# Sphinx configuration for checking the documentation of a rendered instance
# (tests/check_docs.py). It is not part of the instance: the documentation
# is built for real in a separate Sphinx project that copies docs/en and
# docs/de of every instance.
import os
import shlex

project = "IFDD service documentation (check)"
extensions = ["myst_parser", "sphinxcontrib.plantuml"]
exclude_patterns = ["_build"]

# References to other parts of the full documentation (the instance chapter
# ifdd-instances-*, other services, ifdd-be-core) cannot resolve in a build
# of one service; check_docs.py checks the references within the service.
suppress_warnings = ["ref.ref"]

# PlantUML runs locally (java -jar, Graphviz for the layout); no diagram
# server. tests/docs/get_plantuml.sh downloads the pinned jar.
_jar = os.environ.get("IFDD_PLANTUML_JAR", "")
if not _jar or not os.path.isfile(_jar):
    raise RuntimeError(
        'IFDD_PLANTUML_JAR must point to plantuml.jar: '
        'export IFDD_PLANTUML_JAR="$(tests/docs/get_plantuml.sh)"'
    )
plantuml = f"java -jar {shlex.quote(_jar)}"
plantuml_output_format = "svg_img"
