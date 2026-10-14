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

Each updater keeps a single PR open on a fixed branch (`chore/<chart>-update`) and refreshes it when a newer upstream version appears.

The updaters open PRs with `GITHUB_TOKEN`, which requires **Settings → Actions → General → Workflow permissions → "Allow GitHub Actions to create and approve pull requests"**. Alternatively, set a `CHART_UPDATER_TOKEN` secret (fine-grained PAT or GitHub App token with `contents` and `pull-requests` write); PRs opened with it also trigger other workflows.

The release workflow in `.github/workflows/release.yml` publishes chart changes after they land on `master`.
