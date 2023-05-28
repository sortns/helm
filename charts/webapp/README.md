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
| `ingress.enabled` | Ingress functional | `true` |
| `ingress.className` | Ingress className | `` |
| `ingress.annotations.kubernetes.io/ingress.class` | Ingress class | `nginx` |
| `ingress.hosts` | Ingress hosts range | `dev.test.net` |
| `ingress.tls` | Ingress tls | `[]` |
| `service.type` | Type of service | `ClusterIP` |
| `service.port` | Service's port | `80` |
| `topology_max_skew` | Topology spread max skew | `1` |
| `autoscaling` | Autoscalling settings | `{}` |
| `nodeSelector`                                    | Node labels for pod assignment                               |`{}`                                     |
| `tolerations` | Toleration | `[]` |
| `affinity`| Affinity | `{}` | 




Specify each parameter using the `--set key=value[,key=value]` argument to `helm install`. For example:

```bash
$ helm install --name my-release --set image.tag=v0.0.3 stable/webapp
```

Alternatively, a YAML file that specifies the values for the parameters can be provided while
installing the chart. For example:

```bash
$ helm install --name my-release --values values.yaml stable/webapp
```