# Description

webapp chart is a simple chart to deploy web application using own image on k8s

## Prerequisites

- TBA

## Installing the Chart

To install the chart with the release name `my-release`:

```bash
$ helm install TBA --name my-release
```

__Note__: TBA

## Uninstalling the Chart

To uninstall/delete the `my-release` deployment:

```bash
$ helm delete my-release
```

The command removes all the Kubernetes components EXCEPT the persistent volume.

## Updating

TBA

## Configuration

The following table lists the configurable parameters of the webapp chart and their default values. 

| Parameter                                         | Description                                                          | Default                                        |
| ------------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------- |
| `replicaCount`                                    | Number of replicas to create     | `2`                                            |
| `image.repository`                                | container image                                        | `nginx`                 |
| `image.tag`                                       | container image tag                                    | `1.9.1`                                       |
| `image.pullPolicy`                                | container image pull policy                            | `Always`                                 |
| `resources.limits.cpu`                            | CPU limit per zetcd pod                                      | `100m`                                         |
| `resources.limits.memory`                         | Memory limit per zetcd pod                                   | `128mi`                                       |
| `resources.requests.cpu`                          | CPU request per zetcd pod                                    | `50m`                                        |
| `resources.requests.memory`                       | Memory request per zetcd pod                                 | `64mi`                                       |
| `nodeSelector`                                    | Node labels for pod assignment                               |`{}`                                     |
| `host` | Host name for ingress URL application | `dev.test.net` | 
| `service.type` | Type of service | `ClusterIP` |
| `service.port` | Service's port | `80` |
| `topologySpreadConstraints.maxSkew` | Topology spread max skew | `1` |
| `topologySpreadConstraints.topologyKey` | Topology spread key | `kubernetes.io/hostname` |
| `topologySpreadConstraints.whenUnsatisfiable` | Topology spread when unsatisfiable | `DoNotSchedule` |
| `topologySpreadConstraints.whenUnsatisfiable` | Topology spread when unsatisfiable | `DoNotSchedule` |
| `topologySpreadConstraints.labelSelector.matchLabels.app.kubernetes.io/instance` | Topology spread label selector| `webapp` |
| `labels.app`                            | Application label                    | `webapp`                                        |





Specify each parameter using the `--set key=value[,key=value]` argument to `helm install`. For example:

```bash
$ helm install --name my-release --set image.tag=v0.0.3 stable/webapp
```

Alternatively, a YAML file that specifies the values for the parameters can be provided while
installing the chart. For example:

```bash
$ helm install --name my-release --values values.yaml stable/webapp
```