from __future__ import annotations

import contextlib
import inspect
import json
import locale
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Final, Union, final

from typing_extensions import Self

root_dir: Final[Path] = Path(__file__).parent.parent / "i18n"
WINDOWS = sys.platform.startswith("win") or (sys.platform == "cli" and os.name == "nt")


@dataclass
class _LangConfigData:
    default: str | None = None
    frozen: dict[str, list[str]] | None = None
    require: dict[str, list[str]] | None = None
    name: str | None = None

    locales: set[str] = field(default_factory=set)

    def __post_init__(self):
        if isinstance(self.name, str):
            self.name = self.name.strip()
            if not self.name:
                self.name = None


def _get_win_locale_with_ctypes() -> str | None:
    import ctypes

    kernel32 = ctypes.windll.kernel32
    lcid: int = kernel32.GetUserDefaultUILanguage()
    return locale.windows_locale.get(lcid)


def _get_win_locale_from_registry() -> str | None:
    import winreg  # noqa

    with contextlib.suppress(Exception):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International") as key:
            if lcid := winreg.QueryValueEx(key, "Locale")[0]:
                return locale.windows_locale.get(int(lcid, 16))


if WINDOWS:
    try:
        import ctypes  # noqa: F401

        _get_win_locale = _get_win_locale_with_ctypes
    except ImportError:
        _get_win_locale = _get_win_locale_from_registry


def get_locale() -> str | None:
    if WINDOWS:
        return _get_win_locale()

    return locale.getlocale(locale.LC_MESSAGES)[0]  # type: ignore


def _get_config(root: Path) -> _LangConfigData:
    if not (root / ".config.json").exists():
        raise FileNotFoundError(f"Config file not found in {root}")
    with (root / ".config.json").open("r", encoding="utf-8") as f:
        data = json.load(f)
        if "frozen" in data:
            data["frozen"] = _expand(data["frozen"])
        if "require" in data:
            data["require"] = _expand(data["require"])
        return _LangConfigData(**data)


Types = Union[str, dict[str, "Types"]]
Raw = dict[str, dict[str, Types]]


def convert_dictionary(data, prefix: str = ""):
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result.update(convert_dictionary(value, f"{prefix}{key}."))
        else:
            result[f"{prefix}{key}"] = value
    return result


def flatten(data: Raw) -> dict[str, dict[str, str]]:
    result = {}
    for scope, types in data.items():
        result[scope] = {}
        for type, value in types.items():
            if isinstance(value, dict):
                result[scope].update(convert_dictionary({type: value}))
            else:
                result[scope][type] = value
    return result


def merge(source: dict, target: dict) -> dict:
    for key, value in source.items():
        if isinstance(value, dict):
            target[key] = merge(value, target.get(key, {}))
        elif isinstance(value, list):
            target[key] = value + target.get(key, [])
        else:
            target[key] = value
    return target


def _expand(data: list[str]):
    result: dict[str, list[str]] = {}
    for i in data:
        if "." not in i:
            i += ".*"
        parts = i.split(".", 1)
        s = parts[0]
        if s not in result:
            result[s] = []
            if not parts[1].startswith("*"):
                result[s].append(parts[1])
        elif result[s] and not parts[1].startswith("*"):
            result[s].append(parts[1])
    return result


def _get_lang(file: Path) -> Raw:
    if not file.exists():
        raise FileNotFoundError(f"Lang file '{file}' not found")
    if file.suffix.startswith(".json"):
        with file.open("r", encoding="utf-8") as f:
            data: Raw = json.load(f)
        data.pop("$schema", None)
        return data
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required to load yaml file")
    with file.open("r", encoding="utf-8") as f:
        data: Raw = yaml.safe_load(f)
    data.pop("$schema", None)
    return data


def _get_scopes(root: Path) -> dict[str, dict[str, dict[str, str]]]:
    result = {}
    for i in root.iterdir():
        if not i.is_file() or i.name.startswith(".") or i.suffix not in (".json", ".yaml", ".yml"):
            continue
        result[i.stem] = flatten(_get_lang(i))
    return result


@final
class _LangConfig:
    def __init__(self):
        self._root_config = _get_config(root_dir)
        self.__configs: dict[str, _LangConfigData] = {"$root": self._root_config}
        self.__locale: str = self._root_config.default or "en-US"
        self.__default_locale: str = self._root_config.default or "en-US"
        self.__langs: dict[str, dict[str, dict[str, str]]] = _get_scopes(root_dir)
        self.__locales = set(self.__langs.keys())
        self.__frozen: dict[str, list[str]] = (self._root_config.frozen or {}).copy()
        self.callbacks: list[Callable[[str], None]] = []
        self.select_local()

    @property
    def locales(self):
        return set(sorted(self.__locales))  # noqa: C414

    def locales_in(self, config_name: str):
        return self.__configs[config_name].locales

    @property
    def current(self):
        return self.__locale

    def select_local(self):
        """
        依据系统语言尝试自动选择语言
        """
        old = self.__locale
        if (lc := get_locale()) and lc.replace("_", "-") in self.__langs:
            self.__locale = lc.replace("_", "-")
            if old != self.__locale:
                for i in self.callbacks:
                    i(self.__locale)
        return self

    def select(self, locale: str) -> Self:
        old = self.__locale
        locale = locale.replace("_", "-")
        if locale not in self.__langs:
            raise ValueError(self.require("lang", "error.locale").format(target=locale))
        self.__locale = locale
        if old != self.__locale:
            for i in self.callbacks:
                i(self.__locale)
        return self

    def load_data(self, locale: str, data: Raw, config: _LangConfigData | None = None):
        if config:
            config.locales.add(locale)
        if locale in self.__langs:
            source = flatten(data)
            target = self.__langs[locale]
            for scope, ignores in self.__frozen.items():
                if scope not in target or scope not in source:
                    continue
                if not ignores:
                    source.pop(scope)
                else:
                    for i in ignores:
                        source[scope] = {
                            k: v for k, v in source[scope].items() if not (k.startswith(i) and k in target[scope])
                        }
            self.__langs[locale] = merge(source, target)
        else:
            self.__locales.add(locale)
            self.__langs[locale] = flatten(data)
        if not config or not config.require:
            return
        for scope, requries in config.require.items():
            if scope not in self.__langs[locale]:
                raise KeyError(self.require("lang", "miss_require_scope", locale).format(locale=locale, target=scope))
            for t in requries:
                if any(k.startswith(t) for k in self.__langs[locale][scope]):
                    continue
                raise KeyError(
                    self.require("lang", "miss_require_type", locale).format(locale=locale, scope=scope, target=t)
                )

    def load_file(self, filepath: Path, config: _LangConfigData | None = None):
        return self.load_data(filepath.stem, _get_lang(filepath), config)

    def load_config(self, dir_path: Path, config_name: str | None = None):
        config = _get_config(dir_path)
        name = config.name or config_name
        if not name:
            raise ValueError("Config name is required")
        if name.startswith("$"):
            raise ValueError("Config name cannot start with '$'")
        self.__default_locale = config.default or self.__default_locale
        self.__configs[name] = config
        self.__frozen = merge(config.frozen or {}, self.__frozen)
        self.select_local()
        return config

    def load(self, root: Path) -> Self:
        if (cf := inspect.currentframe()) and (fb := cf.f_back):
            mod_name = fb.f_globals["__loader__"].name
            mod_name = mod_name.removesuffix(".i18n")
        else:
            mod_name = None
        config = self.load_config(root, mod_name)
        for i in root.iterdir():
            if not i.is_file() or i.name.startswith(".") or i.suffix not in (".json", ".yaml", ".yml"):
                continue
            self.load_file(i, config)
        return self

    def require(self, scope: str, type: str, locale: str | None = None) -> str:
        locale = locale or self.__locale
        if locale not in self.__langs:
            raise ValueError(self.__langs[self.__locale]["lang"]["error.locale"].format(target=locale))
        if scope in self.__langs[locale]:
            _types = self.__langs[locale][scope]
        elif scope in self.__langs[self.__locale]:
            _types = self.__langs[self.__locale][scope]
        elif scope in self.__langs[self.__default_locale]:
            _types = self.__langs[self.__default_locale][scope]
        else:
            raise ValueError(self.__langs[locale]["lang"]["error.scope"].format(target=scope, locale=locale))
        if type in _types:
            return _types[type]
        elif type in self.__langs[self.__locale][scope]:
            return self.__langs[self.__locale][scope][type]
        elif type in self.__langs[self.__default_locale][scope]:
            return self.__langs[self.__default_locale][scope][type]
        else:
            raise ValueError(self.__langs[locale]["lang"]["error.type"].format(target=type, locale=locale, scope=scope))

    def set(self, scope: str, type: str, content: str, locale: str | None = None):
        locale = locale or self.__locale
        if locale not in self.__langs:
            raise ValueError(self.__langs[self.__locale]["lang"]["error.locale"].format(target=locale))
        if scope in self.__frozen:
            raise ValueError(self.__langs[locale]["lang"]["error.scope"].format(target=scope, locale=locale))
        elif type in self.__frozen.get(scope, []):
            raise ValueError(self.__langs[locale]["lang"]["error.type"].format(target=type, locale=locale, scope=scope))
        self.__langs[locale].setdefault(scope, {})[type] = content

    def __repr__(self):
        return f"<LangConfig: {self.__locale}>"


lang: _LangConfig = _LangConfig()

__all__ = ["lang"]
