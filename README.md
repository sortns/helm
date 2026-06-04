# Helm Charts

## Usage

[Helm](https://helm.sh) must be installed to use the charts.
Please refer to Helm's [documentation](https://helm.sh/docs/) to get started.

Once Helm is set up properly, add the repo as follows:

```console
helm repo add sortns_charts https://sortns.github.io/helm
```

You can then run `helm search repo sortns_charts` to see the charts

## Available charts

| Chart | Description |
| --- | --- |
| `headscale` | Self-hosted Tailscale control plane with optional DERP and UI components |
| `poweradmin` | Production-oriented Poweradmin deployment for PowerDNS with secure secret handling |
| `simple-app` | Generic application deployment starter chart |
| `webapp` | Web application deployment chart |
| `cron-task` | Scheduled workload chart |
| `calico-host-firewall` | Calico host endpoint and policy resources |

## Automated app-version updates

This repository ships dedicated updater workflows for charts that track upstream application releases:

- `headscale`: `.github/workflows/update-headscale.yml`
- `poweradmin`: `.github/workflows/update-poweradmin.yml`

The release workflow in `.github/workflows/release.yml` publishes chart changes after they land on `master`.
