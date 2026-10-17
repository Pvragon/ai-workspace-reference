"""Central user config — NO defaults baked into source.

All operational defaults (location, radius, max age, paths) live in the user's
config file, scaffolded by ``deals init``. The source ships only the *config
schema* and a comment template, never the values. This keeps the San Diego /
92124 reference out of the shipped tool.

Location: $DEALS_CONFIG_DIR or ~/.config/deals/
  config.toml   — user defaults (this module)
  auth.json     — per-site auth/device tokens (deals.auth; gitignored)
  catalogs/     — written CSV catalogs
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

try:                       # py311+
    import tomllib as _toml
    _LOADS = lambda b: _toml.loads(b)            # noqa: E731
except ModuleNotFoundError:  # py<=310
    import tomli as _toml                          # type: ignore
    _LOADS = lambda b: _toml.loads(b)            # noqa: E731


def config_dir() -> Path:
    d = os.environ.get("DEALS_CONFIG_DIR")
    return Path(d).expanduser() if d else Path.home() / ".config" / "deals"


def config_path() -> Path:
    return config_dir() / "config.toml"


def catalogs_dir() -> Path:
    return config_dir() / "catalogs"


# Written verbatim by ``deals init`` after substituting prompted values. The
# {...} placeholders are filled at scaffold time; defaults live HERE, in the
# generated user file — not anywhere in the runtime code path.
CONFIG_TEMPLATE = """\
# deals — user config. Edit freely; every value is overridable per-command.
# Scaffolded by `deals init` on {created}.

[location]
zip = "{zip}"
# lat/lon resolved from zip at init (used to localize marketplace distance).
lat = {lat}
lon = {lon}
name = "{name}"

[defaults]
radius_mi = {radius_mi}     # post-filter: drop listings farther than this
max_age   = "{max_age}"     # post-filter: drop listings older than this (e.g. "2mo", "30d", "6w")
site      = "{site}"        # default marketplace adapter

[output]
# where `scrape` writes catalogs; `export`/`ls` read the latest unless --in given
catalogs_dir = "{catalogs_dir}"
"""


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, data: dict):
        self._d = data

    # --- typed accessors (raise if init hasn't run / value missing) ---
    def _get(self, *keys, default: Any = None, required: bool = False) -> Any:
        node: Any = self._d
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                if required:
                    raise ConfigError(
                        f"config missing [{'.'.join(keys[:-1])}] {keys[-1]} — run `deals init`")
                return default
            node = node[k]
        return node

    @property
    def zip(self) -> str: return str(self._get("location", "zip", required=True))
    @property
    def lat(self) -> float: return float(self._get("location", "lat", required=True))
    @property
    def lon(self) -> float: return float(self._get("location", "lon", required=True))
    @property
    def location_name(self) -> str: return str(self._get("location", "name", default=""))
    @property
    def radius_mi(self) -> float: return float(self._get("defaults", "radius_mi", required=True))
    @property
    def max_age(self) -> str: return str(self._get("defaults", "max_age", required=True))
    @property
    def site(self) -> str: return str(self._get("defaults", "site", default="offerup"))

    @property
    def catalogs_dir(self) -> Path:
        p = self._get("output", "catalogs_dir", default=None)
        return Path(p).expanduser() if p else catalogs_dir()


def load() -> Config:
    p = config_path()
    if not p.exists():
        raise ConfigError(f"no config at {p} — run `deals init` first")
    try:
        data = _LOADS(p.read_text())
    except Exception as e:                     # tomllib/tomli TOMLDecodeError
        raise ConfigError(f"{p} is malformed ({e}) — re-run `deals init --force`")
    return Config(data)


def exists() -> bool:
    return config_path().exists()
