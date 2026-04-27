from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "generate-env-docs.py"
    spec = importlib.util.spec_from_file_location("generate_env_docs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generate_env_docs = _load_module()


def test_settings_parser_reads_env_prefix_and_defaults(tmp_path: Path) -> None:
    config = tmp_path / "config.py"
    config.write_text(
        """
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    jwt_secret_key: str = ""
    access_token_ttl: int = 900
    oauth_state_secret: str = Field(default="abc", description="State signing secret.")
""",
        encoding="utf-8",
    )

    entries = {entry.name: entry for entry in generate_env_docs.parse_settings_entries(config)}

    assert entries["AUTH_JWT_SECRET_KEY"].component == "Auth"
    assert entries["AUTH_JWT_SECRET_KEY"].sensitivity == "sensitive"
    assert entries["AUTH_ACCESS_TOKEN_TTL"].default == "`900`"
    assert entries["AUTH_OAUTH_STATE_SECRET"].description == "State signing secret."


def test_settings_parser_reads_alias_choices(tmp_path: Path) -> None:
    config = tmp_path / "config.py"
    config.write_text(
        """
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class ObjectStorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="S3_", extra="ignore")

    endpoint_url: str = Field(default="", validation_alias=AliasChoices("S3_ENDPOINT_URL", "MINIO_ENDPOINT"))
""",
        encoding="utf-8",
    )

    names = {entry.name for entry in generate_env_docs.parse_settings_entries(config)}

    assert {"S3_ENDPOINT_URL", "MINIO_ENDPOINT"} <= names


def test_python_ast_finds_getenv_environ_get_and_subscript(tmp_path: Path) -> None:
    root = tmp_path / "src"
    root.mkdir()
    (root / "sample.py").write_text(
        """
import os

os.getenv("PLATFORM_ALPHA")
os.getenv("PLATFORM_BETA", "b")
os.environ.get("PLATFORM_GAMMA", "g")
os.environ["PLATFORM_DELTA"]
""",
        encoding="utf-8",
    )

    entries = {entry.name: entry for entry in generate_env_docs.parse_python_env_entries(root)}

    assert entries["PLATFORM_ALPHA"].required == "required"
    assert entries["PLATFORM_BETA"].default == "`b`"
    assert entries["PLATFORM_GAMMA"].default == "`g`"
    assert entries["PLATFORM_DELTA"].required == "required"


def test_go_regex_finds_getenv_and_helper_calls(tmp_path: Path) -> None:
    root = tmp_path / "services"
    root.mkdir()
    (root / "main.go").write_text(
        """
package main

func main() {
    _ = os.Getenv("REDIS_ADDR")
    _ = envString("S3_ENDPOINT_URL", os.Getenv("MINIO_ENDPOINT"))
}
""",
        encoding="utf-8",
    )

    names = {entry.name for entry in generate_env_docs.parse_go_env_entries(root)}

    assert {"REDIS_ADDR", "S3_ENDPOINT_URL", "MINIO_ENDPOINT"} <= names


def test_helm_parser_collects_container_env_names(tmp_path: Path) -> None:
    root = tmp_path / "helm"
    root.mkdir()
    (root / "deployment.yaml").write_text(
        """
env:
  - name: QDRANT_API_KEY
    valueFrom:
      secretKeyRef:
        name: qdrant-api-key
""",
        encoding="utf-8",
    )

    names = {entry.name for entry in generate_env_docs.parse_helm_env_entries(root)}

    assert names == {"QDRANT_API_KEY"}


def test_merge_prefers_settings_metadata_over_raw_calls() -> None:
    raw = generate_env_docs.EnvVarEntry(
        name="REDIS_PASSWORD",
        component="Other",
        required="required",
        default="",
        description="raw",
        sensitivity="sensitive",
        sources={"raw.py"},
    )
    setting = generate_env_docs.EnvVarEntry(
        name="REDIS_PASSWORD",
        component="Redis",
        required="optional",
        default="`\"\"`",
        description="setting",
        sensitivity="sensitive",
        sources={"config.py"},
    )

    [merged] = generate_env_docs.merge_entries([raw, setting])

    assert merged.component == "Redis"
    assert merged.required == "required"
    assert merged.default == "`\"\"`"
    assert merged.sources == {"raw.py", "config.py"}


def test_sensitivity_heuristic() -> None:
    assert generate_env_docs.classify_sensitivity("AUTH_JWT_SECRET_KEY") == "sensitive"
    assert generate_env_docs.classify_sensitivity("POSTGRES_HOST") == "configuration"
    assert generate_env_docs.classify_sensitivity("FEATURE_E2E_MODE") == "informational"


def test_render_markdown_is_deterministic() -> None:
    entries = [
        generate_env_docs.EnvVarEntry(
            name="B_VAR",
            component="Comp",
            required="optional",
            default="",
            description="B",
            sensitivity="informational",
            sources={"b.py"},
        ),
        generate_env_docs.EnvVarEntry(
            name="A_VAR",
            component="Comp",
            required="optional",
            default="",
            description="A",
            sensitivity="informational",
            sources={"a.py"},
        ),
    ]

    first = generate_env_docs.render_markdown(entries)
    second = generate_env_docs.render_markdown(reversed(entries))

    assert first == second
    assert first.index("`A_VAR`") < first.index("`B_VAR`")


def test_collect_env_vars_finds_deduplicated_repo_entries(tmp_path: Path) -> None:
    repo = tmp_path
    config_dir = repo / "apps/control-plane/src/platform/common"
    config_dir.mkdir(parents=True)
    (config_dir / "config.py").write_text(
        """
from pydantic_settings import BaseSettings, SettingsConfigDict

class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")
    password: str = ""
""",
        encoding="utf-8",
    )
    platform_dir = repo / "apps/control-plane/src/platform"
    (platform_dir / "sample.py").write_text('import os\nos.getenv("REDIS_PASSWORD")\n', encoding="utf-8")
    service_dir = repo / "services/svc"
    service_dir.mkdir(parents=True)
    (service_dir / "main.go").write_text('os.Getenv("REDIS_PASSWORD")', encoding="utf-8")

    entries = [entry for entry in generate_env_docs.collect_env_vars(repo) if entry.name == "REDIS_PASSWORD"]

    assert len(entries) == 1
    assert entries[0].component == "Redis"
    assert len(entries[0].sources) == 3


def test_output_contains_required_columns() -> None:
    entry = generate_env_docs.EnvVarEntry(
        name="PLATFORM_TEST",
        component="Platform",
        required="optional",
        default="`false`",
        description="Test.",
        sensitivity="informational",
        sources={"config.py"},
    )

    content = generate_env_docs.render_markdown([entry])

    assert "| Variable | Required | Default | Sensitivity | Description | Sources |" in content
    assert "`PLATFORM_TEST`" in content
