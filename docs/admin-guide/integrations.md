# Integrations

Integration pages cover webhook destinations, notification channels, A2A endpoints, OAuth providers, model providers, and credential references.

## Common Admin Workflows

### Add a Webhook

Create the endpoint, configure signing secret reference, send a verification challenge, and confirm replay protection before enabling delivery.

### Configure Slack or Teams

Register the channel, test delivery, and set retry/dead-letter behavior. Keep channel ownership documented.

### Register an A2A Endpoint

Add endpoint URL, authentication metadata, visibility, and rate limits. Validate with a test task before making it available to creators.

### Rotate Integration Secret

Create the new secret, overlap delivery, verify both sides accept the new credential, and revoke the old secret.
