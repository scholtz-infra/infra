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

Set two repository variables: `K8S_SERVER` (for example `https://k8s.example.com:6443`) and
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

The token is valid for a few minutes, so log in at the start of the deploy job. Storage classes
available to applications: `longhorn` (default, replicated) and `local-path` (node-local, fastest).
