# quarantined-actions

Keeping track of the latest quarantine-cleared versions of various GitHub Actions

https://michael-k.github.io/quarantined-actions/versions.txt

https://michael-k.github.io/quarantined-actions/versions-sha.txt

Access that URL for a list of all of the official Actions belonging to the [GitHub Actions](https://github.com/actions) organization along with their latest version tags that have cleared a 14-day quarantine.

You can point coding agents such as Claude Code and Codex CLI at this URL so they know the most recent Actions versions to use in their workflow files.

## Usage

### Running Locally

To run the script locally and avoid GitHub API rate limits, set a `GITHUB_TOKEN` environment variable:

```bash
export GITHUB_TOKEN=ghp_your_token_here
python3 fetch_versions.py
```

The token is optional - without it, the script works with lower API rate limits (60 requests/hour for unauthenticated requests).

### Output Files

The script generates the following files:

- **`versions.txt`** - Default bundle, exact `vX.Y.Z` tags that have been observed unchanged for at least 14 days (supply-chain quarantine)
- **`versions-sha.txt`** - SHA-pinned format for default bundle
- **`{org}-versions.txt`** - Per-org version files (e.g., `aws-actions-versions.txt`)
- **`{org}-versions-sha.txt`** - Per-org SHA-pinned files
- **`index.json`** - Discovery file listing all available bundles
- **`seen-versions.json`** - Quarantine ledger: every observed `vX.Y.Z` tag, its commit SHA, and the date first seen

Only versions first seen at least 14 days ago, whose commit SHA has stayed
unchanged since, are offered, so a freshly-published (or tampered) release is
never recommended until it has had time to be vetted. If an immutable `vX.Y.Z` tag's
SHA ever changes, that version is permanently withdrawn and a `tag-moved` issue
is opened.

## API

An `index.json` file is available at:

https://michael-k.github.io/quarantined-actions/index.json

This file lists all available bundles and their download URLs.

### Example Response

```json
{
  "bundles": {
    "default": {
      "versions_url": "https://michael-k.github.io/quarantined-actions/versions.txt",
      "versions_sha_url": "https://michael-k.github.io/quarantined-actions/versions-sha.txt"
    }
  },
  "orgs": {
    "aws-actions": {
      "versions_url": "https://michael-k.github.io/quarantined-actions/aws-actions-versions.txt",
      "versions_sha_url": "https://michael-k.github.io/quarantined-actions/aws-actions-versions-sha.txt"
    }
  }
}
```

### Usage Examples

```bash
# Fetch index to discover available bundles
curl -s https://michael-k.github.io/quarantined-actions/index.json | jq '.'

# Get default bundle versions
curl -s https://michael-k.github.io/quarantined-actions/versions.txt

# Get AWS-specific versions
curl -s https://michael-k.github.io/quarantined-actions/aws-actions-versions.txt
```

## Fork Note

This is a personal fork of [acidghost/actions-latest](https://github.com/acidghost/actions-latest), itself a fork of the [actions-latest](https://github.com/simonw/actions-latest) project by [Simon Willison](https://github.com/simonw). Contributions to this fork may not be considered or merged.

<!-- VERSIONS_START -->
## Latest versions

```
actions/add-to-project@v2.0.0
actions/ai-inference@v2.1.1
actions/attest@v4.1.0
actions/attest-build-provenance@v4.1.0
actions/attest-sbom@v4.1.0
actions/cache@v5.0.5
actions/checkout@v6.0.3
actions/configure-pages@v6.0.0
actions/create-github-app-token@v3.2.0
actions/create-release@v1.1.4
actions/delete-package-versions@v5.0.0
actions/dependency-review-action@v5.0.0
actions/deploy-pages@v5.0.0
actions/download-artifact@v8.0.1
actions/first-interaction@v3.1.0
actions/github-script@v9.0.0
actions/go-dependency-submission@v2.0.3
actions/javascript-action@v1.0.1
actions/jekyll-build-pages@v1.0.13
actions/labeler@v6.1.0
actions/setup-dotnet@v5.3.0
actions/setup-elixir@v1.5.0
actions/setup-go@v6.4.0
actions/setup-haskell@v1.1.4
actions/setup-java@v5.3.0
actions/setup-node@v6.4.0
actions/setup-python@v6.2.0
actions/setup-ruby@v1.1.3
actions/stale@v10.3.0
actions/upload-artifact@v7.0.1
actions/upload-code-coverage@v1.3.0
actions/upload-pages-artifact@v5.0.0
actions/upload-release-asset@v1.0.2
```
<!-- VERSIONS_END -->

<!-- VERSIONS_SHA_START -->
## Latest versions (SHA-pinned)

```
actions/add-to-project@5afcf98fcd03f1c2f92c3c83f58ae24323cc57fd # v2.0.0
actions/ai-inference@a7805884c80886efc241e94a5351df715968a0ad # v2.1.1
actions/attest@59d89421af93a897026c735860bf21b6eb4f7b26 # v4.1.0
actions/attest-build-provenance@a2bbfa25375fe432b6a289bc6b6cd05ecd0c4c32 # v4.1.0
actions/attest-sbom@c604332985a26aa8cf1bdc465b92731239ec6b9e # v4.1.0
actions/cache@27d5ce7f107fe9357f9df03efb73ab90386fccae # v5.0.5
actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d # v6.0.0
actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0
actions/create-release@0cb9c9b65d5d1901c1f53e5e66eaf4afd303e70e # v1.1.4
actions/delete-package-versions@e5bc658cc4c965c472efe991f8beea3981499c55 # v5.0.0
actions/dependency-review-action@a1d282b36b6f3519aa1f3fc636f609c47dddb294 # v5.0.0
actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128 # v5.0.0
actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
actions/first-interaction@1c4688942c71f71d4f5502a26ea67c331730fa4d # v3.1.0
actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3 # v9.0.0
actions/go-dependency-submission@f35d5c9af13ce9cc32f7930b171e315e878f6921 # v2.0.3
actions/javascript-action@4be183afbd08ddadedcf09f17e8e112326894107 # v1.0.1
actions/jekyll-build-pages@44a6e6beabd48582f863aeeb6cb2151cc1716697 # v1.0.13
actions/labeler@f27b608878404679385c85cfa523b85ccb86e213 # v6.1.0
actions/setup-dotnet@9a946fdbd5fb07b82b2f5a4466058b876ab72bb2 # v5.3.0
actions/setup-elixir@3c118cec41f6c3bfc2c7f2aef9bec886ab0b2324 # v1.5.0
actions/setup-go@4a3601121dd01d1626a1e23e37211e3254c1c06c # v6.4.0
actions/setup-haskell@048c29979717135f04282c42c2186bb5945b2d8f # v1.1.4
actions/setup-java@ad2b38190b15e4d6bdf0c97fb4fca8412226d287 # v5.3.0
actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e # v6.4.0
actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.2.0
actions/setup-ruby@e932e7af67fc4a8fc77bd86b744acd4e42fe3543 # v1.1.3
actions/stale@eb5cf3af3ac0a1aa4c9c45633dd1ae542a27a899 # v10.3.0
actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
actions/upload-code-coverage@abb5995db9e0199b0e2bb9dbd136fce4cb1ec4d3 # v1.3.0
actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0
actions/upload-release-asset@e8f9f06c4b078e705bd2ea027f0926603fc9b4d5 # v1.0.2
```
<!-- VERSIONS_SHA_END -->

## Orgs

<!-- AWS-ACTIONS_VERSIONS_START -->
<details>
<summary><h3><code>aws-actions</code></h3></summary>

```
aws-actions/amazon-ecr-login@v2.1.6
aws-actions/amazon-ecs-deploy-express-service@v1.2.1
aws-actions/amazon-ecs-deploy-task-definition@v2.6.2
aws-actions/amazon-ecs-render-task-definition@v1.8.5
aws-actions/amazon-eks-fargate@v0.1.1
aws-actions/application-observability-for-aws@v1.1.1
aws-actions/aws-cloudformation-github-deploy@v2.2.0
aws-actions/aws-codebuild-run-build@v1.0.19
aws-actions/aws-elasticbeanstalk-deploy@v1.0.4
aws-actions/aws-lambda-deploy@v1.1.2
aws-actions/aws-secretsmanager-get-secrets@v3.0.1
aws-actions/cloudformation-aws-iam-policy-validator@v1.0.4
aws-actions/codeguru-security@v1.2.2
aws-actions/configure-aws-credentials@v6.2.0
aws-actions/stale-issue-cleanup@v7.1.1
aws-actions/sustainability-scanner@v1.3.1
aws-actions/terraform-aws-iam-policy-validator@v1.0.3
aws-actions/vulnerability-scan-github-action-for-amazon-inspector@v1.5.0
```

</details>
<!-- AWS-ACTIONS_VERSIONS_END -->

<!-- AWS-ACTIONS_VERSIONS_SHA_START -->
<details>
<summary><h3><code>aws-actions</code> (SHA-pinned)</h3></summary>

```
aws-actions/amazon-ecr-login@d539f0932e70871a027e9d5a9d8fc38589180a64 # v2.1.6
aws-actions/amazon-ecs-deploy-express-service@2088fb17efe80c13c2e40a6a1a7e4a4b12f88041 # v1.2.1
aws-actions/amazon-ecs-deploy-task-definition@a310a830f5c14e583e35d84e4e1ec7dd177c3c9c # v2.6.2
aws-actions/amazon-ecs-render-task-definition@6853cfae8c3a7d978fbf68b5a55453395541dfbb # v1.8.5
aws-actions/amazon-eks-fargate@fa91b1ce6e342eb17a1d57df976506d02f074640 # v0.1.1
aws-actions/application-observability-for-aws@95bb59e4538ba9ef746805d8a2bbbe531ba2a728 # v1.1.1
aws-actions/aws-cloudformation-github-deploy@81e3b03d2266bcb76c4bcc37a7d71d9cb67838bb # v2.2.0
aws-actions/aws-codebuild-run-build@7e46c3fa1c1f217e26a73712796b1f78938b534b # v1.0.19
aws-actions/aws-elasticbeanstalk-deploy@1f56e4e813ae4eb167e69ca324234c336c1df573 # v1.0.4
aws-actions/aws-lambda-deploy@d496277188b89f0be02d7a2216fc912c0427702a # v1.1.2
aws-actions/aws-secretsmanager-get-secrets@2cb1a461cbd4865ac4299648312e4704c646cd53 # v3.0.1
aws-actions/cloudformation-aws-iam-policy-validator@aa5ca59693ba89d200db1d2b3af4b60989627bdc # v1.0.4
aws-actions/codeguru-security@44877802cfee29abce47f8ba12b8417d70d01a9b # v1.2.2
aws-actions/configure-aws-credentials@e7f100cf4c008499ea8adda475de1042d6975c7b # v6.2.0
aws-actions/stale-issue-cleanup@0604f2edf84a3a66bc0dfb4a30eb07814cbdf440 # v7.1.1
aws-actions/sustainability-scanner@d6067411fc5290a836e3ebcf388c746d83cf0e9f # v1.3.1
aws-actions/terraform-aws-iam-policy-validator@1cd3c484b95b6c3d9e42ca1797d89ae74eb29ede # v1.0.3
aws-actions/vulnerability-scan-github-action-for-amazon-inspector@f5a63f71de9d790c7c42da74d59efb2c017bdcac # v1.5.0
```

</details>
<!-- AWS-ACTIONS_VERSIONS_SHA_END -->

<!-- ASTRAL-SH_VERSIONS_START -->
<details>
<summary><h3><code>astral-sh</code></h3></summary>

```
astral-sh/attest-action@v0.0.6
astral-sh/pyx-auth-action@v0.0.10
astral-sh/ruff-action@v4.0.0
astral-sh/setup-uv@v8.2.0
```

</details>
<!-- ASTRAL-SH_VERSIONS_END -->

<!-- ASTRAL-SH_VERSIONS_SHA_START -->
<details>
<summary><h3><code>astral-sh</code> (SHA-pinned)</h3></summary>

```
astral-sh/attest-action@f589a42a7efb6fe400b4f400de60b4bc90390027 # v0.0.6
astral-sh/pyx-auth-action@91cba5589c19c6e57e4688208832a1ffd60f9044 # v0.0.10
astral-sh/ruff-action@0ce1b0bf8b818ef400413f810f8a11cdbda0034b # v4.0.0
astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0
```

</details>
<!-- ASTRAL-SH_VERSIONS_SHA_END -->

<!-- DOCKER_VERSIONS_START -->
<details>
<summary><h3><code>docker</code></h3></summary>

```
docker/bake-action@v7.2.0
docker/build-push-action@v7.2.0
docker/cagent-action@v1.5.5
docker/login-action@v4.2.0
docker/metadata-action@v6.1.0
docker/scout-action@v1.21.0
docker/setup-buildx-action@v4.1.0
docker/setup-compose-action@v2.2.0
docker/setup-docker-action@v5.2.0
docker/setup-qemu-action@v4.1.0
```

</details>
<!-- DOCKER_VERSIONS_END -->

<!-- DOCKER_VERSIONS_SHA_START -->
<details>
<summary><h3><code>docker</code> (SHA-pinned)</h3></summary>

```
docker/bake-action@6614cfa25eff9a0b2b2697efb0b6159e7680d584 # v7.2.0
docker/build-push-action@f9f3042f7e2789586610d6e8b85c8f03e5195baf # v7.2.0
docker/cagent-action@367a30ddb41e0156459d03750f508eac03f3c38a # v1.5.5
docker/login-action@650006c6eb7dba73a995cc03b0b2d7f5ca915bee # v4.2.0
docker/metadata-action@80c7e94dd9b9319bd5eb7a0e0fe9291e23a2a2e9 # v6.1.0
docker/scout-action@cd72f264beff1cd72735de31148b9d3244a0234a # v1.21.0
docker/setup-buildx-action@d7f5e7f509e45cec5c76c4d5afdd7de93d0b3df5 # v4.1.0
docker/setup-compose-action@16feee727cbdc83b6a014e6cc26fec4a79bcf30c # v2.2.0
docker/setup-docker-action@0234bb73ccb40f0c430b795634f9247e2b5c2d23 # v5.2.0
docker/setup-qemu-action@06116385d9baf250c9f4dcb4858b16962ea869c3 # v4.1.0
```

</details>
<!-- DOCKER_VERSIONS_SHA_END -->

<!-- GOOGLE-GITHUB-ACTIONS_VERSIONS_START -->
<details>
<summary><h3><code>google-github-actions</code></h3></summary>

```
google-github-actions/analyze-code-security-scc@v1.0.0
google-github-actions/auth@v3.0.0
google-github-actions/create-cloud-deploy-release@v2.0.0
google-github-actions/deploy-appengine@v3.0.1
google-github-actions/deploy-cloud-functions@v4.0.0
google-github-actions/deploy-cloudrun@v3.0.1
google-github-actions/deploy-gke@v0.0.4
google-github-actions/get-gke-credentials@v3.0.0
google-github-actions/get-secretmanager-secrets@v3.0.0
google-github-actions/release-please-action@v4.1.1
google-github-actions/run-gemini-cli@v0.1.22
google-github-actions/run-vertexai-notebook@v1.1.3
google-github-actions/send-google-chat-webhook@v0.0.4
google-github-actions/setup-gcloud@v3.0.1
google-github-actions/ssh-compute@v2.0.0
google-github-actions/test-action@v2.0.1
google-github-actions/upload-cloud-storage@v3.0.0
```

</details>
<!-- GOOGLE-GITHUB-ACTIONS_VERSIONS_END -->

<!-- GOOGLE-GITHUB-ACTIONS_VERSIONS_SHA_START -->
<details>
<summary><h3><code>google-github-actions</code> (SHA-pinned)</h3></summary>

```
google-github-actions/analyze-code-security-scc@b48efb29dbbaabe3d2400d0ad221481100fc83b9 # v1.0.0
google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093 # v3.0.0
google-github-actions/create-cloud-deploy-release@0da6d9c5a288abb58ad78385750dea3ca8c7dcdb # v2.0.0
google-github-actions/deploy-appengine@54d5fc7167ec790eb0233905e3cef384221b4619 # v3.0.1
google-github-actions/deploy-cloud-functions@ab10d6b9be21630aafc15ced4c464c16cd6640d6 # v4.0.0
google-github-actions/deploy-cloudrun@2028e2d7d30a78c6910e0632e48dd561b064884d # v3.0.1
google-github-actions/deploy-gke@838b2722264c927290d85d2e6cb8165d6b509788 # v0.0.4
google-github-actions/get-gke-credentials@3da1e46a907576cefaa90c484278bb5b259dd395 # v3.0.0
google-github-actions/get-secretmanager-secrets@bc9c54b29fdffb8a47776820a7d26e77b379d262 # v3.0.0
google-github-actions/release-please-action@e4dc86ba9405554aeba3c6bb2d169500e7d3b4ee # v4.1.1
google-github-actions/run-gemini-cli@f77273f4c914e4bf38440cf36a0369cb64a37489 # v0.1.22
google-github-actions/run-vertexai-notebook@9322561b61e4c720ac7868db5450409acdfb0131 # v1.1.3
google-github-actions/send-google-chat-webhook@21736222f072d3b7f252ea778ff7098d7aabe85a # v0.0.4
google-github-actions/setup-gcloud@aa5489c8933f4cc7a4f7d45035b3b1440c9c10db # v3.0.1
google-github-actions/ssh-compute@907d824cb3cb1630ddd72c032f8c64be474b4117 # v2.0.0
google-github-actions/test-action@095c7b07bb9ebfd6deeb8bebba2372550a944c15 # v2.0.1
google-github-actions/upload-cloud-storage@6397bd7208e18d13ba2619ee21b9873edc94427a # v3.0.0
```

</details>
<!-- GOOGLE-GITHUB-ACTIONS_VERSIONS_SHA_END -->

<!-- HASHICORP_VERSIONS_START -->
<details>
<summary><h3><code>hashicorp</code></h3></summary>

```
hashicorp/actions-slack-status@v2.0.1
hashicorp/setup-boundary@v1.1.0
hashicorp/setup-nomad@v1.0.0
hashicorp/setup-packer@v3.3.0
hashicorp/terraform-cdk-action@v11.0.2
hashicorp/vault-action@v4.0.0
```

</details>
<!-- HASHICORP_VERSIONS_END -->

<!-- HASHICORP_VERSIONS_SHA_START -->
<details>
<summary><h3><code>hashicorp</code> (SHA-pinned)</h3></summary>

```
hashicorp/actions-slack-status@1a3f63b30bd476aee1f3bd6f9d8f2aacc4f14d81 # v2.0.1
hashicorp/setup-boundary@8373fde01681beb0bfa40e3d3e9a84f3a3cb8283 # v1.1.0
hashicorp/setup-nomad@ceba9087d4322dbdd7b35dafac5a87a8c459a157 # v1.0.0
hashicorp/setup-packer@3286471d6cc6756d056a0b199fea5e0becdbc189 # v3.3.0
hashicorp/terraform-cdk-action@ec317e0c5cebab5b15bd676bbcc8e0afdbc96142 # v11.0.2
hashicorp/vault-action@892a26828f195e65540a40b4768ae4571f51ebfc # v4.0.0
```

</details>
<!-- HASHICORP_VERSIONS_SHA_END -->

<!-- AZURE_VERSIONS_START -->
<details>
<summary><h3><code>Azure</code></h3></summary>

```
Azure/aca-review-apps@v0.2.1
Azure/aks-set-context@v5.0.0
Azure/bicep-build-action@v1.0.1
Azure/bicep-deploy@v2.3.0
Azure/data-factory-deploy-action@v1.2.0
Azure/data-factory-export-action@v1.2.1
Azure/data-factory-validate-action@v1.1.6
Azure/deployment-what-if-action@v1.0.0
Azure/k8s-bake@v4.1.0
Azure/k8s-create-secret@v6.0.0
Azure/k8s-deploy@v6.0.0
Azure/k8s-lint@v4.0.0
Azure/k8s-set-context@v5.0.0
Azure/login@v3.0.0
Azure/setup-helm@v5.0.0
Azure/setup-kubectl@v5.1.0
Azure/sql-action@v2.2.1
```

</details>
<!-- AZURE_VERSIONS_END -->

<!-- AZURE_VERSIONS_SHA_START -->
<details>
<summary><h3><code>Azure</code> (SHA-pinned)</h3></summary>

```
Azure/aca-review-apps@edb566ff1c235496327839df6c82713cbe9e93ac # v0.2.1
Azure/aks-set-context@60623acbdcbbdcf799ad50a1adf8703874339f8b # v5.0.0
Azure/bicep-build-action@d2a88e5c7150cd562f3e8b8f361560db2cb4d5c5 # v1.0.1
Azure/bicep-deploy@66910e9c5c7733c33a1cd605030d02234b3bc4ed # v2.3.0
Azure/data-factory-deploy-action@390b7811bd2e99d4b8cef1bff69dab47bb5872ce # v1.2.0
Azure/data-factory-export-action@64109498d635d1ad6b6d78bdae3c1460c8d42d06 # v1.2.1
Azure/data-factory-validate-action@1a1e93960902bd7de128c22b985fb6256988af4b # v1.1.6
Azure/deployment-what-if-action@7caef615e35c10abe2d2dd2ec811071697e9d723 # v1.0.0
Azure/k8s-bake@0191a5ae5126cfe61885d9bd46511caa8e9a9550 # v4.1.0
Azure/k8s-create-secret@5e49ad902ac755e0815974a44904c728da961747 # v6.0.0
Azure/k8s-deploy@c7ebd0d5f39477a23f1b5dea0f52e6db04adf28e # v6.0.0
Azure/k8s-lint@e4234c50ea835112e72b145bdecd00a94bad42fd # v4.0.0
Azure/k8s-set-context@89b837d75b40a7bd2ddafde837473c212db8b313 # v5.0.0
Azure/login@532459ea530d8321f2fb9bb10d1e0bcf23869a43 # v3.0.0
Azure/setup-helm@dda3372f752e03dde6b3237bc9431cdc2f7a02a2 # v5.0.0
Azure/setup-kubectl@829323503d1be3d00ca8346e5391ca0b07a9ab0d # v5.1.0
Azure/sql-action@96cea35f2b24c72eb5b6ece33d45e6f60e6b7b87 # v2.2.1
```

</details>
<!-- AZURE_VERSIONS_SHA_END -->
