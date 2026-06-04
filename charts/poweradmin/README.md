# Poweradmin Helm Chart

This chart deploys [Poweradmin](https://github.com/poweradmin/poweradmin) on Kubernetes with production-oriented defaults:

- non-root container execution on port `8080`
- read-only root filesystem with writable runtime mounts only where required
- file-based secret injection using Poweradmin's `__FILE` support
- a database bootstrap init container for Poweradmin `4.2.3`
- optional SQLite PVC for lab or single-node setups
- external MySQL/PostgreSQL support for production
- optional ingress, PDB, and network policy resources

The chart targets Poweradmin `4.2.3` and follows the stable `4.2.x` line.

## Version note

Upstream versioning is a little inconsistent across release surfaces. This chart is pinned to `4.2.3` because that stable image tag is published upstream, while the GitHub releases page may lag behind specific stable-line tags.

The `4.2.3` image does not include the database auto-initialization logic that exists in newer upstream builds, so this chart performs schema bootstrap in an init container before the application starts.

## Installing

```bash
helm install poweradmin ./charts/poweradmin
```

## Recommended production setup

Use MySQL or PostgreSQL, keep `persistence.enabled=false`, and provide secrets through `secretEnv.values` or an externally managed Secret.

Minimal MySQL example:

```yaml
env:
  DB_TYPE: mysql
  DB_HOST: mysql.example.svc
  DB_PORT: "3306"
  DB_USER: poweradmin
  DB_NAME: poweradmin
  DNS_NS1: ns1.example.com
  DNS_NS2: ns2.example.com
  DNS_HOSTMASTER: hostmaster.example.com
  PA_APPLICATION_URL: https://dns.example.com
  PA_CREATE_ADMIN: "true"

secretEnv:
  values:
    DB_PASS: change-me
    PA_SESSION_KEY: replace-with-long-random-secret

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: dns.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: poweradmin-tls
      hosts:
        - dns.example.com
```

## SQLite example

SQLite is useful for evaluation or small single-instance deployments.

```yaml
env:
  DB_TYPE: sqlite
  DB_FILE: /db/pdns.db
  DNS_NS1: ns1.example.com
  DNS_NS2: ns2.example.com
  DNS_HOSTMASTER: hostmaster.example.com
  PA_CREATE_ADMIN: "true"

persistence:
  enabled: true
  size: 8Gi

secretEnv:
  values:
    PA_SESSION_KEY: replace-with-long-random-secret
```

## Secrets

Sensitive values are not injected directly as plain env vars by default. Instead, the chart:

1. stores them in a Kubernetes `Secret`
2. mounts that secret under `secretEnv.mountPath`
3. sets `VAR__FILE` env vars pointing to the mounted files

This matches upstream Poweradmin container support documented in `DOCKER-SECRETS.md`.

To use an existing Secret:

```yaml
secretEnv:
  existingSecret: poweradmin-secrets
  existingSecretKeys:
    DB_PASS: DB_PASS
    PA_SESSION_KEY: PA_SESSION_KEY
    PA_PDNS_API_KEY: PA_PDNS_API_KEY
```

## Configuration surface

`values.yaml` includes the currently documented Docker environment variables for:

- database and DNS backend settings
- UI and API settings
- LDAP, OIDC, and SAML authentication
- logging, security, MFA, password recovery, and mail
- optional modules and PowerDNS API integration

Use `extraEnv` for one-off pod env additions that are not Poweradmin settings.

## Probes

The chart defaults to `tcpSocket` probes instead of HTTP `/` probes. Poweradmin serves `/` through application code, and on an uninitialized database that path can generate repeated SQL errors and noisy logs even when the web server itself is healthy.

## Auto-update flow

This repository includes `.github/workflows/update-poweradmin.yml`, modeled after the `headscale` updater. It tracks the highest upstream `v4.2.x` tag and opens a pull request that bumps:

- `charts/poweradmin/Chart.yaml` `appVersion`
- `charts/poweradmin/Chart.yaml` chart version
- `charts/poweradmin/values.yaml` default image tag
