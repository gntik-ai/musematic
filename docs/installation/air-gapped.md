# Air-Gapped Installation

Air-gapped installs require a prepared image mirror, offline Helm dependencies, and offline secret seeding.

## Prepare Connected Media

1. Pull every platform, data-store, and observability image.
2. Mirror images into the target registry namespace.
3. Package Helm charts and dependencies.
4. Export required Python and tool artifacts for any operator scripts.
5. Record checksums for all bundles.

## Install Offline

Configure image registry overrides in Helm values, seed Kubernetes secrets from the offline secret process, install data services, then install observability and the platform chart.

## Verify

Run the same smoke tests as connected installations. Additionally verify no pod tries to pull from the public internet and no egress policy allows unintended outbound traffic.
