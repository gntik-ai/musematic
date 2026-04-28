# Musematic Public Status

`apps/web-status` is the independently deployed public status surface for Musematic.
It builds as a static Next.js export and is served separately from the authenticated
application so visitors can inspect platform state during main-app outages.

## Development

```sh
pnpm install
pnpm --filter @musematic/web-status dev
```

The development server listens on port 3001.

## Production Build

```sh
pnpm --filter @musematic/web-status build
```

The exported site is written to `out/`. Runtime deployments mount a generated
`last-known-good.json` at the web root so the client can render the latest cached
snapshot if the public status API is unreachable.
