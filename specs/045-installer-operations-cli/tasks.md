# Tasks: Installer and Operations CLI

**Input**: Design documents from `specs/045-installer-operations-cli/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in this phase)
- **[Story]**: Which user story this task belongs to (US1–US8 from spec.md)

---

## Phase 1: Setup (Package Scaffold)

**Purpose**: Create `apps/ops-cli/` package with Typer entry point, configuration loader, component registry, and output formatters. After this phase, `platform-cli --help` works.

- [X] T001 Create `apps/ops-cli/pyproject.toml` with all dependencies (typer[all], pydantic, pydantic-settings, pyyaml, jinja2, httpx, asyncpg, redis, grpcio, grpcio-health-checking, cryptography, aioboto3), dev dependencies (pytest, pytest-asyncio, pytest-cov, ruff, mypy), and entry point `platform-cli = "platform_cli.main:app"`
- [X] T002 Create package structure: `apps/ops-cli/src/platform_cli/__init__.py` (with `__version__`), and all `__init__.py` files for subpackages: `commands/`, `installers/`, `preflight/`, `diagnostics/`, `diagnostics/checks/`, `backup/`, `backup/stores/`, `migrations/`, `secrets/`, `checkpoint/`, `locking/`, `helm/`, `output/`
- [X] T003 Create `apps/ops-cli/src/platform_cli/main.py` — Typer app with `app = typer.Typer(name="platform-cli")`; register 5 command groups as sub-apps: `install`, `diagnose`, `backup`, `upgrade`, `admin`; add global options callback for `--config`, `--verbose`, `--json`, `--no-color`; set up Rich console or NDJSON output based on `--json` flag
- [X] T004 [P] Create `apps/ops-cli/src/platform_cli/config.py` — `InstallerConfig` Pydantic BaseSettings model with all fields from data-model.md (`deployment_mode`, `namespace`, `storage_class`, `ingress`, `admin`, `secrets`, `resources`, `image_registry`, `image_tag`, `air_gapped`, `local_registry`, `data_dir`); `load_config(path: Path | None) -> InstallerConfig` function that reads YAML file, merges with env vars (prefix `PLATFORM_CLI_`), and validates
- [X] T005 [P] Create `apps/ops-cli/src/platform_cli/constants.py` — `PLATFORM_COMPONENTS: list[PlatformComponent]` registry defining all 12 components in dependency order (postgresql → redis → kafka → qdrant → neo4j → clickhouse → opensearch → minio → runtime-controller → reasoning-engine → simulation-controller → control-plane) with `name`, `display_name`, `category`, `helm_chart`, `namespace`, `depends_on`, `health_check_type`, `health_check_target`, `has_migration`, `backup_supported` fields per data-model.md
- [X] T006 [P] Create `apps/ops-cli/src/platform_cli/output/console.py` — Rich-based output helpers: `print_status(component, status, latency)`, `print_step(index, total, component, status, duration)`, `print_table(headers, rows)`, `print_credentials_panel(email, password, url)`, `print_error(message, remediation)`, `create_progress()` returning Rich Progress bar
- [X] T007 [P] Create `apps/ops-cli/src/platform_cli/output/structured.py` — NDJSON output: `emit(stage, component, status, message, details)` that writes one JSON line per event to stdout with timestamp, level, stage, component, status, message, details fields per contracts/cli-commands.md structured log format
- [X] T008 Create `apps/ops-cli/tests/conftest.py` — shared pytest fixtures: `tmp_config` (temporary InstallerConfig), `mock_subprocess` (patch subprocess.run), `ndjson_capture` (capture structured output lines)

**Checkpoint**: `platform-cli --help` works; config loads from YAML + env vars.

---

## Phase 2: Foundational (Shared Infrastructure Modules)

**Purpose**: Preflight checks, secret generation, checkpoint/resume, and distributed locking — reused by all installers and commands.

**CRITICAL**: No user story work can begin until this phase is complete.

- [X] T009 Create `apps/ops-cli/src/platform_cli/preflight/base.py` — `PreflightCheck` Protocol with `name: str`, `description: str`, `async check() -> PreflightResult`; `PreflightRunner` class that takes `list[PreflightCheck]`, runs all checks, returns pass/fail summary; `PreflightResult` dataclass with `passed: bool`, `message: str`, `remediation: str | None`
- [X] T010 [P] Create `apps/ops-cli/src/platform_cli/preflight/kubernetes.py` — 4 checks: `KubectlAccessCheck` (run `kubectl cluster-info`), `NamespacePermissionCheck` (dry-run create namespace), `StorageClassCheck` (list StorageClasses, verify configured class exists), `IngressControllerCheck` (list IngressClasses)
- [X] T011 [P] Create `apps/ops-cli/src/platform_cli/preflight/docker.py` — 2 checks: `DockerDaemonCheck` (run `docker info`), `ComposeVersionCheck` (run `docker compose version`, verify v2+)
- [X] T012 [P] Create `apps/ops-cli/src/platform_cli/preflight/local.py` — 2 checks: `DiskSpaceCheck` (verify ≥2GB free in data_dir), `PortAvailabilityCheck` (verify port 8000 and Qdrant port 6333 are free)
- [X] T013 [P] Create `apps/ops-cli/src/platform_cli/secrets/generator.py` — `generate_secrets(config: SecretsConfig) -> GeneratedSecrets`: for each secret field in SecretsConfig, use provided value if non-None, else generate via `secrets.token_urlsafe(24)` (32-char passwords); generate RSA 4096-bit key pair via `cryptography.hazmat.primitives.asymmetric.rsa`; `store_secrets_kubernetes(secrets, namespace)` (create K8s Secret via kubectl), `store_secrets_env_file(secrets, path)` (write .env), `store_secrets_local(secrets, data_dir)` (write JSON)
- [X] T014 [P] Create `apps/ops-cli/src/platform_cli/checkpoint/manager.py` — `CheckpointManager`: `create(config, steps) -> InstallationCheckpoint` (new JSON file at `~/.platform-cli/checkpoints/{uuid}.json`), `update_step(name, status, error?)`, `load_latest(config_hash) -> InstallationCheckpoint | None` (find matching checkpoint by config hash), `get_resume_point() -> str | None` (first non-completed step); config drift detection via SHA-256 of serialized InstallerConfig
- [X] T015 [P] Create `apps/ops-cli/src/platform_cli/locking/kubernetes.py` — `KubernetesLock`: `acquire(namespace, holder_id, timeout_minutes=30) -> bool` (create ConfigMap `platform-install-lock` with holder annotation; fail if already exists and not expired), `release(namespace, holder_id)` (delete ConfigMap if holder matches), `is_locked(namespace) -> tuple[bool, str | None]` (check existence and holder)
- [X] T016 [P] Create `apps/ops-cli/src/platform_cli/locking/file.py` — `FileLock`: `acquire(path=~/.platform-cli/install.lock, timeout_minutes=30) -> bool` (fcntl.flock LOCK_EX | LOCK_NB; write PID + timestamp), `release()` (unlock + delete), `is_locked() -> bool`

**Checkpoint**: All infrastructure modules ready — installer implementations can begin.

---

## Phase 3: User Story 1 — Install Platform on Kubernetes (Priority: P1) 🎯 MVP

**Goal**: `platform-cli install kubernetes` deploys all 12 components, runs migrations, creates admin.

**Independent Test**: Run `platform-cli install kubernetes --dry-run`. Verify preflight checks run. Verify Helm values rendered. Run against a real cluster — verify all services healthy, admin can log in. Run again — verify idempotent.

- [X] T017 [US1] Create `apps/ops-cli/src/platform_cli/helm/renderer.py` — `render_values(component: PlatformComponent, config: InstallerConfig, secrets: GeneratedSecrets) -> dict`: load `deploy/helm/{component.helm_chart}/values.yaml` as base; overlay config overrides from `InstallerConfig.resources[component.name]`; inject secrets (passwords, keys) into appropriate value paths; return merged dict; `write_values_file(values: dict, path: Path)` writes YAML
- [X] T018 [P] [US1] Create `apps/ops-cli/src/platform_cli/helm/runner.py` — `HelmRunner`: `install(chart_path, release_name, namespace, values_file, dry_run=False)` → `subprocess.run(["helm", "upgrade", "--install", release_name, chart_path, "-n", namespace, "-f", values_file, "--create-namespace", "--wait", "--timeout", "5m"])` with error handling; `wait_for_ready(deployment_name, namespace, timeout=300)` → `kubectl rollout status`; `is_installed(release_name, namespace) -> bool` → `helm list`
- [X] T019 [P] [US1] Create `apps/ops-cli/src/platform_cli/migrations/runner.py` — `MigrationRunner`: `run_alembic(database_url)` → `subprocess.run(["alembic", "upgrade", "head"])` using Alembic config from `apps/control-plane/`; `init_qdrant(url)` → create collections via httpx POST; `init_neo4j(url, password)` → create constraints via neo4j-driver; `init_clickhouse(url)` → create tables via clickhouse-connect; `init_opensearch(url)` → create index templates via httpx PUT; `init_kafka(bootstrap)` → create topics via AdminClient; `init_minio(endpoint, access_key, secret_key)` → create buckets via aioboto3; `create_admin_user(api_url, email, password)` → POST to control plane /api/v1/accounts/register + activate
- [X] T020 [US1] Create `apps/ops-cli/src/platform_cli/installers/base.py` — `AbstractInstaller` Protocol with methods: `async preflight()`, `generate_secrets() -> GeneratedSecrets`, `async deploy(secrets)`, `async migrate(secrets)`, `async create_admin(secrets)`, `async verify()`, `async run()` (orchestrates the full flow with checkpoint tracking)
- [X] T021 [US1] Create `apps/ops-cli/src/platform_cli/installers/kubernetes.py` — `KubernetesInstaller(AbstractInstaller)`: acquire K8s lock → run PreflightRunner(kubernetes checks) → generate_secrets() → create K8s namespaces (platform-data, platform-execution, platform-control, platform-simulation, platform-edge, platform-observability) → store secrets → deploy each component in PLATFORM_COMPONENTS order (HelmRunner.install + wait_for_ready, checkpoint after each) → MigrationRunner (Alembic + all init scripts) → create_admin → verify (run DiagnosticRunner) → release lock; support `--dry-run` (render values only), `--resume` (load checkpoint), `--skip-preflight`, `--skip-migrations`
- [X] T022 [US1] Create `apps/ops-cli/src/platform_cli/commands/install.py` — Typer sub-app `install_app = typer.Typer()`; `install kubernetes` command with all flags from contracts/cli-commands.md (`--namespace`, `--storage-class`, `--dry-run`, `--resume`, `--air-gapped`, `--local-registry`, `--image-tag`, `--skip-preflight`, `--skip-migrations`); load config → instantiate KubernetesInstaller → call `installer.run()` → display results via console/structured output; handle errors with appropriate exit codes
- [X] T023 [US1] Wire install command group into `apps/ops-cli/src/platform_cli/main.py` via `app.add_typer(install_app, name="install")`

**Checkpoint**: `platform-cli install kubernetes` works end-to-end.

---

## Phase 4: User Story 2 — Install Platform Locally (Priority: P1)

**Goal**: `platform-cli install local` starts platform in <30 seconds.

**Independent Test**: Run `platform-cli install local` on a machine with no infrastructure. Verify platform starts in <30s. Access the API. Run a basic operation. Stop with `platform-cli admin stop`.

- [X] T024 [US2] Create `apps/ops-cli/src/platform_cli/installers/local.py` — `LocalInstaller(AbstractInstaller)`: run PreflightRunner(local checks) → create `data_dir` structure (db/, storage/, logs/) → init SQLite database (write `DATABASE_URL=sqlite+aiosqlite:///{data_dir}/db/platform.db`) → start in-memory Qdrant subprocess (`qdrant --storage :memory:` or skip if binary not found) → generate secrets (local file storage) → build env var dict overriding all service URLs to local fallbacks per research.md Decision 9 → start control plane subprocess (`uvicorn platform.main:create_app --host 0.0.0.0 --port {port}` with env vars) → wait for `http://localhost:{port}/health` (max 30s) → run Alembic migrations against SQLite → create admin user → write PID file → display credentials; `stop()` method: read PID file → kill process → clean up
- [X] T025 [US2] Add `install local` subcommand to `apps/ops-cli/src/platform_cli/commands/install.py` with flags `--data-dir`, `--port`, `--foreground`; load config → instantiate LocalInstaller → call `installer.run()`
- [X] T026 [P] [US2] Create `apps/ops-cli/src/platform_cli/commands/admin.py` — Typer sub-app `admin_app = typer.Typer()`; `admin stop` command: read PID from `~/.platform-cli/data/platform.pid` → send SIGTERM → wait for exit → report; wire into main.py via `app.add_typer(admin_app, name="admin")`

---

## Phase 5: User Story 3 — Diagnose Platform Health (Priority: P1)

**Goal**: `platform-cli diagnose` checks all components in <30 seconds with green/yellow/red output.

**Independent Test**: Run `platform-cli diagnose` against a running platform. Verify all components show status. Stop one service — re-run, verify red status. Run with `--json` — verify valid JSON.

- [X] T027 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/postgresql.py` — `PostgreSQLCheck`: connect via asyncpg, execute `SELECT 1`, measure latency; return `DiagnosticCheck` with healthy/unhealthy status; catch connection errors → unhealthy with remediation message
- [X] T028 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/redis.py` — `RedisCheck`: connect via redis-py async, execute `PING`, measure latency
- [X] T029 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/kafka.py` — `KafkaCheck`: connect via aiokafka AdminClient, `list_topics()`, measure latency
- [X] T030 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/qdrant.py` — `QdrantCheck`: GET `/healthz` via httpx, measure latency
- [X] T031 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/neo4j.py` — `Neo4jCheck`: connect via neo4j-driver async, execute `RETURN 1`, measure latency
- [X] T032 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/clickhouse.py` — `ClickHouseCheck`: connect via clickhouse-connect, execute `SELECT 1`, measure latency
- [X] T033 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/opensearch.py` — `OpenSearchCheck`: GET `/_cluster/health` via httpx, map cluster status to CheckStatus (green→healthy, yellow→degraded, red→unhealthy)
- [X] T034 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/minio.py` — `MinIOCheck`: HEAD default bucket via aioboto3, measure latency
- [X] T035 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/grpc_services.py` — `GrpcServiceCheck(port, name)`: gRPC health check using `grpcio-health-checking` standard proto against runtime-controller (50051), reasoning-engine (50052), simulation-controller (50055), and sandbox-manager (50053) when that chart exists
- [X] T036 [P] [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checks/model_providers.py` — `ModelProviderCheck(url)`: HTTP GET to configured model provider health endpoint; timeout=5s
- [X] T037 [US3] Create `apps/ops-cli/src/platform_cli/diagnostics/checker.py` — `DiagnosticRunner`: build check list from PLATFORM_COMPONENTS + model providers; `async run(timeout_per_check=5) -> DiagnosticReport`: `asyncio.gather(*[asyncio.wait_for(check.run(), timeout) for check in checks])`, catch TimeoutError → unknown status; compute `overall_status` as worst across all checks; `auto_fix(report) -> list[AutoFixResult]`: for unhealthy K8s deployments → `kubectl rollout restart`, for stuck Redis locks → `DEL`, for missing Kafka topics → recreate
- [X] T038 [US3] Create `apps/ops-cli/src/platform_cli/commands/diagnose.py` — Typer command `diagnose` with flags `--deployment-mode`, `--fix`, `--timeout`, `--checks`; auto-detect deployment mode from context (kubeconfig present → kubernetes, PID file present → local, docker socket → docker); instantiate DiagnosticRunner → `asyncio.run(runner.run())` → format output via console (Rich table) or structured (JSON); exit code: 0 if all healthy, 3 if any degraded/unhealthy; wire into main.py
- [X] T039 [US3] Wire diagnose command into `apps/ops-cli/src/platform_cli/main.py`

---

## Phase 6: User Story 4 — Backup and Restore (Priority: P2)

**Goal**: `platform-cli backup create/restore/list` for all data stores.

**Independent Test**: Run `platform-cli backup create --tag test`. Verify artifacts created for each store. Run `platform-cli backup list` — verify backup appears. Run `platform-cli backup restore <id> --verify-only` — verify checksums pass.

- [X] T040 [P] [US4] Create `apps/ops-cli/src/platform_cli/backup/stores/postgresql.py` — `PostgreSQLBackup`: `backup(output_dir) -> BackupArtifact`: run `pg_dump --format=custom -f {path}` via subprocess; compute SHA-256; return artifact with size and checksum; `restore(artifact_path)`: verify checksum → `pg_restore --clean --if-exists -d {dbname} {path}`
- [X] T041 [P] [US4] Create `apps/ops-cli/src/platform_cli/backup/stores/redis.py` — `RedisBackup`: `backup()`: trigger `BGSAVE` → wait for `LASTSAVE` to change → copy RDB file; `restore()`: stop Redis → replace RDB → restart
- [X] T042 [P] [US4] Create `apps/ops-cli/src/platform_cli/backup/stores/qdrant.py` — `QdrantBackup`: `backup()`: POST `/collections/{name}/snapshots` via httpx → download snapshot file; `restore()`: upload snapshot → POST restore
- [X] T043 [P] [US4] Create `apps/ops-cli/src/platform_cli/backup/stores/neo4j.py` — `Neo4jBackup`: `backup()`: run `neo4j-admin database dump` via subprocess; `restore()`: `neo4j-admin database load`
- [X] T044 [P] [US4] Create `apps/ops-cli/src/platform_cli/backup/stores/clickhouse.py` — `ClickHouseBackup`: `backup()`: run `clickhouse-backup create` via subprocess; `restore()`: `clickhouse-backup restore`
- [X] T045 [P] [US4] Create `apps/ops-cli/src/platform_cli/backup/stores/opensearch.py` — `OpenSearchBackup`: `backup()`: PUT `/_snapshot/platform_backup/{snapshot_name}` via httpx (using MinIO as snapshot repository); `restore()`: POST `/_snapshot/platform_backup/{snapshot_name}/_restore`
- [X] T046 [P] [US4] Create `apps/ops-cli/src/platform_cli/backup/stores/minio.py` — `MinIOBackup`: `backup()`: `mc mirror` source bucket → backup directory via subprocess or aioboto3 copy; `restore()`: mirror back
- [X] T047 [US4] Create `apps/ops-cli/src/platform_cli/backup/manifest.py` — `BackupManifestManager`: `create(backup_id, tag, artifacts) -> BackupManifest`: compute total size, assign sequence number (scan existing manifests), write JSON manifest to backup storage; `load(backup_id) -> BackupManifest`: read from storage; `list(limit=20) -> list[BackupManifest]`: scan backup storage for all manifests, sorted by sequence number desc
- [X] T048 [US4] Create `apps/ops-cli/src/platform_cli/backup/orchestrator.py` — `BackupOrchestrator`: `create(config, tag, stores_filter) -> BackupManifest`: warn if active executions (query control plane API) unless `--force`; iterate PLATFORM_COMPONENTS where `backup_supported`, run each store's `backup()` sequentially, collect artifacts, write manifest; `restore(backup_id, stores_filter, verify_only) -> bool`: load manifest, verify all checksums first (halt if any fail), then restore each store sequentially; `list()` → delegate to ManifestManager
- [X] T049 [US4] Create `apps/ops-cli/src/platform_cli/commands/backup.py` — Typer sub-app `backup_app = typer.Typer()`; `backup create` with `--tag`, `--stores`, `--storage-location`, `--force`; `backup restore BACKUP_ID` with `--stores`, `--verify-only`, `--force`; `backup list` with `--limit`; wire into main.py via `app.add_typer(backup_app, name="backup")`

---

## Phase 7: User Story 5 — Docker / Swarm / Incus Installers (Priority: P2)

**Goal**: `platform-cli install docker/swarm/incus` deploys platform on alternative targets.

**Independent Test**: Run `platform-cli install docker`. Verify Docker Compose file generated. Verify all containers start. Run diagnose — verify healthy.

- [X] T050 [P] [US5] Create `apps/ops-cli/src/platform_cli/installers/docker.py` — `DockerComposeInstaller(AbstractInstaller)`: preflight (docker + compose checks) → generate secrets (store as .env) → render docker-compose.yml from Jinja2 template (12 services with dependency order, volume mounts, env vars, health checks) → `docker compose -p {project} up -d` → wait for all services healthy → run migrations → create admin → display credentials
- [X] T051 [P] [US5] Create `apps/ops-cli/src/platform_cli/installers/swarm.py` — `SwarmInstaller(AbstractInstaller)`: preflight (docker swarm info) → generate secrets (docker secret create) → render stack YAML → `docker stack deploy -c {stack_file} {stack_name}` → wait → migrate → admin
- [X] T052 [P] [US5] Create `apps/ops-cli/src/platform_cli/installers/incus.py` — `IncusInstaller(AbstractInstaller)`: preflight (incus --version) → generate secrets → create profiles → launch containers → run setup scripts inside containers → migrate → admin
- [X] T053 [US5] Add `install docker`, `install swarm`, `install incus` subcommands to `apps/ops-cli/src/platform_cli/commands/install.py` with appropriate flags per cli-commands.md; each creates the corresponding installer and calls `installer.run()`

---

## Phase 8: User Story 6 — Upgrade Platform (Priority: P2)

**Goal**: `platform-cli upgrade` performs rolling upgrades with migration and health verification.

**Independent Test**: Install a version. Run `platform-cli upgrade --dry-run` — verify plan displayed. Run upgrade — verify components updated in order. Run diagnose — verify healthy.

- [X] T054 [US6] Create `apps/ops-cli/src/platform_cli/commands/upgrade.py` — Typer command `upgrade` with `--target-version`, `--dry-run`, `--skip-backup`, `--force`; detect current version (read Helm release metadata via `helm list --output json`) → build `UpgradePlan` listing each component's current vs target version → display plan (dry-run exits here) → create pre-upgrade backup (unless `--skip-backup`) → iterate components in dependency order: `helm upgrade --install` with new image tag → `kubectl rollout status` → checkpoint; after all components: run pending Alembic migrations → verify via DiagnosticRunner; on failure: halt, report failed component, print rollback instructions (`helm rollback {release} {revision}`); wire into main.py

---

## Phase 9: User Story 7 — Headless CI/CD Automation (Priority: P3)

**Goal**: All commands work with `--json` output, env-var config, no prompts, and correct exit codes.

**Independent Test**: Run `PLATFORM_CLI_JSON=true PLATFORM_CLI_DEPLOYMENT_MODE=local platform-cli install local` with no terminal. Verify exit code 0. Parse stdout as NDJSON. Verify all stages present.

- [X] T055 [US7] Audit all commands in `apps/ops-cli/src/platform_cli/commands/install.py`, `diagnose.py`, `backup.py`, `upgrade.py`, `admin.py` for headless compliance: ensure no `typer.confirm()` calls without `--force` bypass; ensure all output routes through `console.py` or `structured.py` (never bare `print()`); ensure exit codes match contracts (0=success, 1=error, 2=preflight, 3=partial); verify all config flags have `PLATFORM_CLI_` env var equivalents via Pydantic settings
- [X] T056 [US7] Add uninstall capability to `apps/ops-cli/src/platform_cli/commands/install.py` — `install uninstall` subcommand: for Kubernetes → `helm uninstall` each release in reverse dependency order → delete namespaces; for Docker → `docker compose down -v`; for local → `admin stop` + delete data dir; requires `--force` in headless mode

---

## Phase 10: User Story 8 — Administer Platform (Priority: P3)

**Goal**: `platform-cli admin` subcommands for user management and status.

**Independent Test**: Run `platform-cli admin status` — verify platform summary. Run `platform-cli admin users list` — verify user table. Run `platform-cli admin users create` — verify new user.

- [X] T057 [US8] Extend `apps/ops-cli/src/platform_cli/commands/admin.py` with `admin users list` subcommand: GET `/api/v1/accounts/users` (with optional `--role` and `--status` filters) → display Rich table or JSON; `admin users create EMAIL --role ROLE` subcommand: POST `/api/v1/accounts/register` → display created user with password; `admin status` subcommand: GET `/health` + `/api/v1/dashboard/metrics` → display version, deployment mode, component count, active executions, uptime as Rich panel or JSON

---

## Phase 11: PyInstaller Standalone Binary

**Goal**: Single-file binary distributable without Python.

- [X] T058 Create `apps/ops-cli/platform-cli.spec` — PyInstaller spec file with `Analysis(["src/platform_cli/__main__.py"])`, hiddenimports for pydantic, rich, typer, cryptography, grpcio, asyncpg, redis, httpx, aioboto3, yaml, jinja2; `EXE` with `name="platform-cli"`, `onefile=True`, `console=True`
- [X] T059 [P] Create `.github/workflows/build-cli.yml` — GitHub Actions workflow: trigger on tag `cli-v*`; matrix build for linux-amd64, linux-arm64, darwin-amd64, darwin-arm64; steps: checkout → setup Python 3.12 → pip install pyinstaller + package → pyinstaller platform-cli.spec → upload binary as release artifact

---

## Phase 12: Tests & Polish

**Goal**: ≥95% test coverage; ruff lint; mypy strict.

- [X] T060 Write unit tests in `apps/ops-cli/tests/unit/test_config.py` — test YAML loading, env var override, Pydantic validation, defaults, invalid config errors
- [X] T061 [P] Write unit tests in `apps/ops-cli/tests/unit/test_preflight.py` — mock subprocess for kubectl/docker/disk checks; test pass/fail/remediation for each PreflightCheck; test PreflightRunner aggregation
- [X] T062 [P] Write unit tests in `apps/ops-cli/tests/unit/test_secrets.py` — test password length and character set; test RSA key pair generation and PEM format; test store_secrets_env_file output format; test provided-vs-generated secret merging
- [X] T063 [P] Write unit tests in `apps/ops-cli/tests/unit/test_checkpoint.py` — test create/update/load cycle; test config drift detection (modified config → new checkpoint); test resume point calculation
- [X] T064 [P] Write unit tests in `apps/ops-cli/tests/unit/test_diagnostics.py`, `test_diagnostic_failures.py`, and `test_branch_closure.py` — mock each health check (healthy, unhealthy, timeout); test DiagnosticRunner.run() concurrency; test overall_status aggregation; test auto_fix action dispatch
- [X] T065 [P] Write unit tests in `apps/ops-cli/tests/unit/test_backup.py` and `test_branch_closure.py` — mock store backup/restore methods; test sequential orchestration; test checksum verification; test manifest creation and listing; test partial failure handling
- [X] T066 [P] Write unit tests in `apps/ops-cli/tests/unit/test_helm.py` and `test_renderer_and_runner_branches.py` — test values.yaml merging; test secret injection; test resource override application; test write_values_file YAML validity
- [X] T067 [P] Write unit tests in `apps/ops-cli/tests/unit/test_output.py` — test Rich console output formatting (capture output); test NDJSON structured output (parse each line as JSON, verify schema)
- [X] T068 Write integration test in `apps/ops-cli/tests/integration/test_install_local.py` — test LocalInstaller start/stop lifecycle with real SQLite (skip Qdrant if binary not available); verify PID file created; verify admin credentials returned; verify stop kills process
- [X] T069 [P] Write integration test in `apps/ops-cli/tests/integration/test_diagnose_live.py` — test DiagnosticRunner against a minimal set of real services (SQLite at minimum); verify report structure and exit codes
- [X] T070 Run `ruff check apps/ops-cli/src/ apps/ops-cli/tests/` and fix all lint errors
- [X] T071 Run `mypy apps/ops-cli/src/ --strict` and fix all type errors

---

## Dependencies

```text
Phase 1 (Setup) → Phase 2 (Foundational) → Phases 3–10 (User Stories)
                                         ↓
                                   Phase 11 (PyInstaller) → Phase 12 (Tests)

Story dependencies:
  US1 (T017–T023) — independent; core MVP
  US2 (T024–T026) — independent; requires Phase 2
  US3 (T027–T039) — independent; requires Phase 2
  US4 (T040–T049) — independent; requires Phase 2
  US5 (T050–T053) — requires US1 (reuses HelmRunner, MigrationRunner patterns)
  US6 (T054)      — requires US1 (HelmRunner) + US3 (DiagnosticRunner) + US4 (backup)
  US7 (T055–T056) — requires US1–US4 complete (audits all commands)
  US8 (T057)      — independent; requires Phase 2
```

## Parallel Execution Per Story

**Phase 2**: T010–T016 all parallel (independent files)  
**Phase 3 (US1)**: T017 + T018 + T019 parallel, then T020, then T021, then T022–T023  
**Phase 4 (US2)**: T024 then T025 + T026 parallel  
**Phase 5 (US3)**: T027–T036 all parallel (10 check modules), then T037, then T038–T039  
**Phase 6 (US4)**: T040–T046 all parallel (7 store modules), then T047, then T048, then T049  
**Phase 7 (US5)**: T050 + T051 + T052 all parallel, then T053  
**Phase 12 (Tests)**: T061–T067 + T069 all parallel, then T070–T071  

## Implementation Strategy

**MVP (Phase 1 + 2 + 3)**: Package scaffold + infrastructure + Kubernetes installer — operators can install platform on K8s.  
**Increment 2 (Phase 4 + 5)**: Local installer + diagnose — developers can run locally and verify health.  
**Increment 3 (Phase 6)**: Backup/restore — disaster recovery capability.  
**Increment 4 (Phase 7 + 8)**: Docker/Swarm/Incus + upgrade — broader deployment targets and version management.  
**Increment 5 (Phase 9 + 10)**: Headless + admin — CI/CD and operational administration.  
**Increment 6 (Phase 11 + 12)**: Binary build + tests + polish.

## Task Summary

| Phase | Tasks | Count |
|-------|-------|-------|
| Phase 1 — Setup | T001–T008 | 8 |
| Phase 2 — Foundational | T009–T016 | 8 |
| Phase 3 — US1 K8s Install | T017–T023 | 7 |
| Phase 4 — US2 Local Install | T024–T026 | 3 |
| Phase 5 — US3 Diagnose | T027–T039 | 13 |
| Phase 6 — US4 Backup/Restore | T040–T049 | 10 |
| Phase 7 — US5 Docker/Swarm/Incus | T050–T053 | 4 |
| Phase 8 — US6 Upgrade | T054 | 1 |
| Phase 9 — US7 Headless | T055–T056 | 2 |
| Phase 10 — US8 Admin | T057 | 1 |
| Phase 11 — PyInstaller | T058–T059 | 2 |
| Phase 12 — Tests & Polish | T060–T071 | 12 |
| **Total** | | **71** |
