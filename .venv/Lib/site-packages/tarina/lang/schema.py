import json
from pathlib import Path
from typing import TypedDict, Union, cast


class _Subtypes(TypedDict):
    subtype: str
    types: list[Union[str, "_Subtypes"]]


class _TemplateDict(TypedDict):
    scope: str
    types: list[Union[str, "_Subtypes"]]


def get_template(root: Path):
    if not (root / ".template.json").exists():
        raise FileNotFoundError(f"Lang Template file not found in {root}")
    with (root / ".template.json").open("r", encoding="utf-8") as f:
        return cast(dict, json.load(f))


def schema_scope(scope: str, types: list[Union[str, "_Subtypes"]]):
    schema = {
        "title": scope.capitalize(),
        "description": f"Scope '{scope}' of lang item",
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    }
    for t in types:
        if isinstance(t, str):
            schema["properties"][t] = {"title": t, "description": f"value of lang item type '{t}'", "type": "string"}
        else:
            schema["properties"][t["subtype"]] = schema_scope(t["subtype"], t["types"])
    return schema


def generate_lang_schema(root: Path):
    template = get_template(root)
    if "scopes" not in template:
        raise KeyError("Template file must have a 'scopes' key")
    scopes: list[_TemplateDict] = template["scopes"]
    return {
        "title": "Lang Schema",
        "description": "Schema for lang file",
        "type": "object",
        "properties": {s["scope"]: schema_scope(s["scope"], s["types"]) for s in scopes},
    }


def write_lang_schema(root: Path):
    schema = generate_lang_schema(root)
    with (root / ".lang.schema.json").open("w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
