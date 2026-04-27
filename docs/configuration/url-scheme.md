# URL Scheme

FR-613 defines the canonical production and development URL scheme.

| Surface | Production | Development Pattern |
| --- | --- | --- |
| Web app | `https://app.musematic.ai` | `https://dev.app.musematic.ai` or local `http://localhost:8080` |
| API | `https://api.musematic.ai` | `https://dev.api.musematic.ai` or local control-plane port |
| Grafana | `https://grafana.musematic.ai` | `https://dev.grafana.musematic.ai` |
| Docs | `https://docs.musematic.ai` or GitHub Pages fallback | Preview artifacts in CI |

Cookie domains should not be shared between production and development. CORS should allow only the configured app origin for the target environment. OAuth redirect URIs must be registered per environment and should never point production providers at development hosts.

Use wildcard DNS only for environments that have explicit TLS automation and ownership controls.
