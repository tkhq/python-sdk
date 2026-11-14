"""Checks for TurnkeyBaseModel's defer_build setting.

Subprocess checks run in a fresh interpreter, so no model has been built yet.
"""

import inspect
import json
import subprocess
import sys

import pytest
from pydantic import BaseModel

import turnkey_sdk_types.generated.types as T

# Heaviest models (activity and result types) plus every Nth model by name.
HEAVY = ["v1Activity", "v1ActivityResponse", "v1Result", "v1Intent"]
SAMPLE_EVERY = 25

_LIST_MODELS = """
import inspect
from pydantic import BaseModel
import turnkey_sdk_types.generated.types as T
models = sorted(
    (n, o) for n, o in vars(T).items()
    if inspect.isclass(o) and issubclass(o, BaseModel) and o.__module__ == T.__name__
)
"""


def _models():
    return sorted(
        (n, o)
        for n, o in vars(T).items()
        if inspect.isclass(o)
        and issubclass(o, BaseModel)
        and o.__module__ == T.__name__
    )


def _run(code: str, *args: str) -> dict:
    out = subprocess.run(
        [sys.executable, "-c", code, *args], capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def test_every_model_builds():
    # Definition order, so dependencies are usually built before the models using them.
    models = [
        (n, o)
        for n, o in vars(T).items()
        if inspect.isclass(o)
        and issubclass(o, BaseModel)
        and o.__module__ == T.__name__
    ]
    for name, cls in models:
        cls.model_rebuild(force=True)
        assert cls.__pydantic_complete__, name


def test_serialize_before_validate():
    # Pydantic 2.1-2.2 crashed here with deferred building.
    code = (
        _LIST_MODELS
        + """
import json
failed = []
for n, cls in models:
    try:
        cls.model_construct().model_dump(warnings=False)
    except Exception as e:
        failed.append([n, type(e).__name__, str(e)[:200]])
print(json.dumps({"failed": failed}))
"""
    )
    assert _run(code)["failed"] == []


def _sample(schema, defs, seen=()):
    """Build input data that should validate against a JSON schema."""
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return None if name in seen else _sample(defs[name], defs, seen + (name,))
    for key in ("allOf", "anyOf"):
        if key in schema:
            opts = [o for o in schema[key] if o.get("type") != "null"]
            return _sample(opts[0], defs, seen) if opts else None
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:  # single-value enums on older Pydantic
        return schema["const"]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        out = {}
        for k, v in schema.get("properties", {}).items():
            val = _sample(v, defs, seen)
            if val is not None or k in schema.get("required", []):
                out[k] = val
        return out
    if t == "array":
        item = _sample(schema.get("items", {}), defs, seen)
        return [] if item is None else [item]
    return {"integer": 1, "number": 1.5, "boolean": True}.get(t, "x")


# Runs in a fresh interpreter with defer_build on or off. Validates and dumps
# first, while models are still unbuilt, then generates schemas.
_COMPARE = """
import json, sys
import pydantic
if sys.argv[1] == "off":
    pydantic.VERSION = "2.4.0"  # makes _DEFER_BUILD False
from pydantic import ValidationError
import turnkey_sdk_types.generated.types as T

def errors(cls, data):
    try:
        cls.model_validate(data)
    except ValidationError as e:
        return [[d["type"], list(d["loc"]), d["msg"]] for d in e.errors()]
    return None

samples = json.load(sys.stdin)
out = {"defer": T.TurnkeyBaseModel.model_config.get("defer_build"), "models": {}}
for n, data in samples.items():
    cls = getattr(T, n)
    r = {}
    try:
        m = cls.model_validate(data)
        r["dump"] = m.model_dump(mode="json")
        r["dump_alias"] = m.model_dump(by_alias=True, exclude_none=True, mode="json")
        r["dump_json"] = m.model_dump_json(by_alias=True)
    except ValidationError:
        r["sample_errors"] = errors(cls, data)
    r["empty_errors"] = errors(cls, {})
    r["wrong_type_errors"] = errors(cls, {k: [[]] for k in data or {}})
    r["not_dict_errors"] = errors(cls, "x")
    r["schemas"] = [
        cls.model_json_schema(mode="validation"),
        cls.model_json_schema(mode="serialization"),
    ]
    out["models"][n] = r
print(json.dumps(out))
"""


@pytest.mark.skipif(not T._DEFER_BUILD, reason="defer_build is off below Pydantic 2.5")
def test_same_behavior_with_defer_off():
    names = [n for i, (n, _) in enumerate(_models()) if i % SAMPLE_EVERY == 0]
    names += HEAVY
    samples = {}
    for n in names:
        schema = getattr(T, n).model_json_schema(by_alias=True)
        samples[n] = _sample(schema, schema.get("$defs", {}))

    def run(mode):
        out = subprocess.run(
            [sys.executable, "-c", _COMPARE, mode],
            input=json.dumps(samples),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(out.stdout)

    on, off = run("on"), run("off")
    assert on["defer"] is True
    assert off["defer"] is False

    # Guard against the check passing because most samples were rejected.
    valid = [n for n, r in on["models"].items() if "dump" in r]
    assert len(valid) >= 0.9 * len(names), sorted(set(names) - set(valid))

    for n in names:
        assert on["models"][n] == off["models"][n], n
