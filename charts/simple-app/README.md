# Description

Flexible application chart is a simple chart to deploy application using own image on k8s. 

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

The following table lists the configurable parameters of the application chart and their default values. 

| Parameter                                         | Description                                                          | Default                                        |
| ------------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------- |
|`serviceAccount.create`| TRUE/FALSE if SA should be created | `false`|
|`serviceAccount.annotations`||`{}`|
|`serviceAccount.name`| SA name|""|
| `deployment.replicaCount`| Number of replicas to create     | `2`                                            |
| `deployment.image.repository`                                | container image                                        | `nginx`                 |
| `deployment.image.tag`                                       | container image tag                                    | `1.9.1`                                       |
| `deployment.image.pullPolicy`                                | container image pull policy                            | `Always`                                 |
| `deployment.resources.limits.cpu`                            | CPU limit per zetcd pod                                      | `{}`                                         |
| `deployment.resources.limits.memory`                         | Memory limit per zetcd pod                                   | `{}`                                       |
| `deployment.resources.requests.cpu`                          | CPU request per zetcd pod                                    | `{}`                                        |
| `deployment.resources.requests.memory`                       | Memory request per zetcd pod                                 | `{}`                                       |
|`deployment.secret.enabled`| If need to create secret for Custome Image Repository | `false`|
|`deployment.secret.app_imagePullSecrets_name`| Image repository name | `false`|
|`deployment.secret.app_imagePullSecrets`| Image repository name (must be the smae as above) | `nginx-registry`|
|`deployment.secret.app_dockerconfigjson`| Base64 encoded auth credential | `fake base64 cred`|
| `ingress.enabled` | Ingress functional | `false` |
| `ingress.className` | Ingress className | `` |
| `ingress.annotations.kubernetes.io/ingress.class` | Ingress class | `nginx` |
| `ingress.hosts` | Ingress hosts range | `dev.test.net` |
| `ingress.tls` | Ingress tls | `[]` |
| `service.type` | Type of service | `ClusterIP` |
| `service.port` | Service's port | `80` |
| `deployment.topology_max_skew` | Topology spread max skew | `1` |
| `hpa.autoscaling` | Autoscalling settings | `{}` |
| `deployment.nodeSelector`                                    | Node labels for pod assignment                               |`{}`                                     |
| `deployment.tolerations` | Toleration | `[]` |
| `deployment.affinity`| Affinity | `{}` | 




Specify each parameter using the `--set key=value[,key=value]` argument to `helm install`. For example:

```bash
$ helm install --name my-release --set image.tag=v0.0.3 stable/application
```

Alternatively, a YAML file that specifies the values for the parameters can be provided while
installing the chart. For example:

```bash
$ helm install --name my-release --values values.yaml stable/application
```