"""Q-Orca config loader — YAML config + ORCA_* env var override precedence."""

import os
from functools import cache
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from q_orca.config.types import QOrcaConfig, DEFAULT_CONFIG


_env_loaded = False


def _load_env_file() -> None:
    """Load .env file from current working directory."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True

    cwd = Path.cwd()
    env_path = cwd / ".env"
    if not env_path.exists():
        return

    content = env_path.read_text()
    for line in content.split("\n"):
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        eq_index = trimmed.find("=")
        if eq_index == -1:
            continue
        key = trimmed[:eq_index].strip()
        value = trimmed[eq_index + 1 :].strip()
        # Remove surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _interpolate_env_vars(obj):
    """Recursively replace ${VAR_NAME} in config values with env var values."""
    if isinstance(obj, str):
        import re

        def replacer(match):
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ValueError(f"Environment variable {var_name} is not set")
            return value

        return re.sub(r"\$\{([^}]+)\}", replacer, obj)
    if isinstance(obj, list):
        return [_interpolate_env_vars(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _interpolate_env_vars(v) for k, v in obj.items()}
    return obj


def _deep_merge(target: QOrcaConfig, source: QOrcaConfig) -> QOrcaConfig:
    """Merge source into target, skipping None values."""
    result_dict = {}
    for key in target.__dataclass_fields__:
        target_val = getattr(target, key)
        source_val = getattr(source, key, None)
        if source_val is not None and source_val != "":
            result_dict[key] = source_val
        else:
            result_dict[key] = target_val
    return QOrcaConfig(**result_dict)


def _find_project_config() -> Path | None:
    """Find project config in current working directory."""
    cwd = Path.cwd()
    for name in ["orca.yaml", ".orca.yaml", "orca/orca.yaml"]:
        path = cwd / name
        if path.exists():
            return path
    return None


@cache
def load_config(config_path: str | None = None) -> QOrcaConfig:
    """Load Q-Orca config with precedence: global YAML → project YAML → ORCA_* env vars."""
    _load_env_file()

    configs: list[QOrcaConfig] = []

    # 1. Global default
    # 2. Project config
    project_path = Path(config_path) if config_path else _find_project_config()
    if project_path and project_path.exists() and HAS_YAML:
        parsed = yaml.safe_load(project_path.read_text())
        if parsed:
            parsed = _interpolate_env_vars(parsed)
            configs.append(QOrcaConfig(**{k: v for k, v in parsed.items() if k in QOrcaConfig.__dataclass_fields__}))

    # Merge YAML configs onto DEFAULT_CONFIG first
    result = DEFAULT_CONFIG
    for config in configs:
        result = _deep_merge(result, config)

    # 3. Environment variable overrides (highest precedence)
    #    Applied as dict overrides on the already-merged result to avoid
    #    constructing a partial QOrcaConfig (which would fail since
    #    provider and model are required positional args).
    env_overrides: dict = {}
    if os.environ.get("ORCA_PROVIDER"):
        provider = os.environ["ORCA_PROVIDER"]
        valid_providers = ("anthropic", "openai", "ollama", "grok", "minimax")
        if provider not in valid_providers:
            raise ValueError(f"ORCA_PROVIDER must be one of {valid_providers}")
        env_overrides["provider"] = provider
    if os.environ.get("ORCA_MODEL"):
        env_overrides["model"] = os.environ["ORCA_MODEL"]
    if os.environ.get("ORCA_BASE_URL"):
        env_overrides["base_url"] = os.environ["ORCA_BASE_URL"]
    if os.environ.get("ORCA_API_KEY"):
        env_overrides["api_key"] = os.environ["ORCA_API_KEY"]
    if os.environ.get("ORCA_CODE_GENERATOR"):
        env_overrides["code_generator"] = os.environ["ORCA_CODE_GENERATOR"]
    if os.environ.get("ORCA_MAX_TOKENS"):
        env_overrides["max_tokens"] = int(os.environ["ORCA_MAX_TOKENS"])
    if os.environ.get("ORCA_TEMPERATURE"):
        env_overrides["temperature"] = float(os.environ["ORCA_TEMPERATURE"])

    if env_overrides:
        # Build final config by overlaying env overrides onto the merged result
        result_dict = {k: getattr(result, k) for k in result.__dataclass_fields__}
        result_dict.update(env_overrides)
        result = QOrcaConfig(**result_dict)

    return result


def resolve_config_overrides(
    config: QOrcaConfig, overrides: QOrcaConfig
) -> QOrcaConfig:
    """Apply runtime overrides to a config."""
    return _deep_merge(config, overrides)
