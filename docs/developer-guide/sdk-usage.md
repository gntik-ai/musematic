# SDK Usage

Client SDKs should be generated or validated from the committed OpenAPI snapshot. The docs build fails when `docs/api-reference/openapi.json` drifts from the FastAPI app.

Recommended client behavior:

- Send bearer tokens on every authenticated request.
- Preserve and log correlation IDs.
- Retry idempotent reads with exponential backoff.
- Do not retry unsafe writes unless the endpoint documents idempotency.
- Handle unknown response fields and enum values.
- Surface stable error codes to users and logs.

Use the generated `x-codeSamples` in the API Reference for language-specific request shapes.
