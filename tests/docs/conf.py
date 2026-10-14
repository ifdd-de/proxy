# Sphinx configuration for checking the documentation of a rendered instance
# (tests/check_docs.py). It is not part of the instance: the documentation
# is built for real in a separate Sphinx project that copies docs/en and
# docs/de of every instance.
project = "IFDD service documentation (check)"
extensions = ["myst_parser", "sphinxcontrib.mermaid"]
exclude_patterns = ["_build"]

# References to other parts of the full documentation (the instance chapter
# ifdd-instances-*, other services, ifdd-be-core) cannot resolve in a build
# of one service; check_docs.py checks the references within the service.
suppress_warnings = ["ref.ref"]
