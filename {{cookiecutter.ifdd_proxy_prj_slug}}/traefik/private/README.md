# Instance-specific dynamic configuration

Every `*.yml` file in this directory is loaded by Traefik's file provider in
production (mounted at `/etc/traefik/dynamic/private`). Files with other
extensions, such as this README or `*.dist` examples, are ignored.

Typical content: the certificate list (`certificates.yml`, from the `.dist`
example), additional routers or middlewares that only this instance needs.

This directory is on the cruft skip list, so `cruft update` never touches it.
Nothing here is secret - private keys belong in `certs/`, passwords in
`secrets/`, and both are git-ignored.
