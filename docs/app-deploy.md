# Deploying an application from its own repository

Application repositories do not need a kubeconfig or any stored cluster credential. A workflow
proves its identity to the Kubernetes API with its GitHub Actions OIDC token and becomes the
user `github:<owner>/<repo>`, which is allowed to manage exactly one namespace.

## 1. Grant access (in this repository)

Add the repository to `platform/tenants.yml` and run the `platform` playbook:

```yaml
tenants:
  - namespace: my-app
    repository: scholtz-infra/my-app
```

The owner (`scholtz-infra`) must be listed in `github_oidc_allowed_owners`.

## 2. Workflow in the application repository

Set two repository variables: `K8S_SERVER` (for example `https://k8s.biatec.io:53831`) and
`K8S_CA` (the cluster CA certificate, base64 encoded: the `certificate-authority-data` value of
the cluster kubeconfig; it is not a secret).

```yaml
permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Log in to the cluster
        run: |
          token=$(curl -sSf -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=k8s-prod" | jq -r .value)
          echo "::add-mask::$token"
          echo "${{ vars.K8S_CA }}" | base64 -d > "$RUNNER_TEMP/ca.crt"
          kubectl config set-cluster prod --server="${{ vars.K8S_SERVER }}" --certificate-authority="$RUNNER_TEMP/ca.crt"
          kubectl config set-credentials github --token="$token"
          kubectl config set-context prod --cluster=prod --user=github --namespace=my-app
          kubectl config use-context prod
      - run: kubectl apply -f k8s/
```

## Exposing a website (Ingress and certificate)

Ask for your namespace to be added to `network_web` in `platform/network.yml` of the infra
repository, point the hostname at the load balancer in Cloudflare (`A 167.235.110.199`,
`AAAA 2a01:4f8:1c1f:690b::1`), then add an Ingress. Only HTTPS on port 443 is served; there is
no port 80. The
certificate is requested from Let's Encrypt automatically and renewed before it expires.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt   # use letsencrypt-staging while testing
spec:
  ingressClassName: cilium
  tls:
    - hosts: [my-app.example.com]
      secretName: my-app-tls
  rules:
    - host: my-app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  number: 80
```

## Network isolation

Pods in your namespace can talk to each other, to cluster DNS and to the internet. Nothing from
another namespace can reach them, and they cannot reach services in other namespaces (for example
a shared Redis), until the pair is listed in `platform/network.yml` in the infra repository.
Blocked connections time out. Pods must satisfy the `baseline` pod security standard (no host
network, host paths or privileged containers).

The token is valid for a few minutes, so log in at the start of the deploy job. Storage classes
available to applications: `longhorn` (default, replicated) and `local-path` (node-local, fastest).
