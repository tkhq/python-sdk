"""Checks for the opt-in TURNKEY_SDK_DEFER_BUILD setting.

Subprocess checks run in a fresh interpreter, because the setting is read once
at import.
"""

import inspect
import json
import os
import subprocess
import sys

import pytest
from pydantic import VERSION as PYDANTIC_VERSION
from pydantic import BaseModel

import turnkey_sdk_types.generated.types as T

ENV_VAR = "TURNKEY_SDK_DEFER_BUILD"

# Every 25th model plus the heaviest ones: 58 of 1,326 (about 4%).
HEAVY = ["v1Activity", "v1ActivityResponse", "v1Result", "v1Intent"]
SAMPLE_EVERY = 25

SUPPORTS_DEFER = tuple(int(p) for p in PYDANTIC_VERSION.split(".")[:2]) >= (2, 5)
needs_defer = pytest.mark.skipif(
    not SUPPORTS_DEFER, reason="defer_build needs Pydantic 2.5+"
)


def _models():
    """Generated models, in definition order."""
    return [
        (n, o)
        for n, o in vars(T).items()
        if inspect.isclass(o)
        and issubclass(o, BaseModel)
        and o.__module__ == T.__name__
    ]


def _names():
    return [n for n, _ in _models()]


def _run(code, stdin_obj, env_value, *args):
    """Run code in a fresh interpreter, with ENV_VAR set to env_value (None unsets it)."""
    env = {k: v for k, v in os.environ.items() if k != ENV_VAR}
    if env_value is not None:
        env[ENV_VAR] = env_value
    out = subprocess.run(
        [sys.executable, "-c", code, *args],
        input=json.dumps(stdin_obj),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(out.stdout)


# Imports the models and reports the mode, how many models were built at
# import, and any warnings about the setting. With "old_pydantic", it reports a
# Pydantic version below 2.5 so that path runs on any installed version.
_IMPORT = """
import json, sys, warnings
import pydantic
if "old_pydantic" in sys.argv:
    pydantic.VERSION = "2.4.0"
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    import turnkey_sdk_types.generated.types as T
names = json.load(sys.stdin)
print(json.dumps({
    "config_keys": sorted(T.TurnkeyBaseModel.model_config),
    "defer_build": T.TurnkeyBaseModel.model_config.get("defer_build"),
    "built": sum(getattr(T, n).__pydantic_complete__ for n in names),
    "warnings": [str(w.message) for w in caught if "TURNKEY_SDK_DEFER_BUILD" in str(w.message)],
}))
"""


@pytest.fixture(scope="module")
def baseline():
    """Import with the setting unset."""
    return _run(_IMPORT, _names(), None)


def test_off_by_default(baseline):
    # Same config as before the setting existed, so models build at import.
    assert baseline["config_keys"] == ["populate_by_name"]
    assert baseline["warnings"] == []


@pytest.mark.parametrize("value", ["0", "false"])
def test_off_values_match_default(value, baseline):
    assert _run(_IMPORT, _names(), value) == baseline


@needs_defer
@pytest.mark.parametrize("value", ["1", "True"])
def test_opt_in_defers(value):
    assert _run(_IMPORT, _names(), value) == {
        "config_keys": ["defer_build", "populate_by_name"],
        "defer_build": True,
        "built": 0,
        "warnings": [],
    }


def test_unrecognized_value_warns_and_stays_off(baseline):
    assert _run(_IMPORT, _names(), "yes") == {
        **baseline,
        "warnings": [
            "Ignoring TURNKEY_SDK_DEFER_BUILD='yes': expected 1, true, 0 or false."
        ],
    }


def test_opt_in_on_old_pydantic_warns_and_stays_off(baseline):
    assert _run(_IMPORT, _names(), "1", "old_pydantic") == {
        **baseline,
        "warnings": [
            "TURNKEY_SDK_DEFER_BUILD needs Pydantic 2.5+ (found 2.4.0); "
            "building models at import."
        ],
    }


@needs_defer
def test_every_model_builds_when_deferred():
    # Definition order, so dependencies are usually built before the models using them.
    code = """
import json, sys
import turnkey_sdk_types.generated.types as T
failed = []
for n in json.load(sys.stdin):
    cls = getattr(T, n)
    try:
        cls.model_rebuild(force=True)
    except Exception as e:
        failed.append([n, type(e).__name__, str(e)[:200]])
    else:
        if not cls.__pydantic_complete__:
            failed.append([n, "incomplete", ""])
print(json.dumps(failed))
"""
    assert _run(code, _names(), "1") == []


@needs_defer
def test_serialize_before_validate_when_deferred():
    # Pydantic 2.1-2.2 crashed here with deferred building.
    code = """
import json, sys
import turnkey_sdk_types.generated.types as T
failed = []
for n in json.load(sys.stdin):
    try:
        getattr(T, n).model_construct().model_dump(warnings=False)
    except Exception as e:
        failed.append([n, type(e).__name__, str(e)[:200]])
print(json.dumps(failed))
"""
    assert _run(code, _names(), "1") == []


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


# Validates and dumps first, while models are still unbuilt when deferred,
# then generates schemas.
_COMPARE = """
import json, sys
from pydantic import ValidationError
import turnkey_sdk_types.generated.types as T

def errors(cls, data):
    try:
        cls.model_validate(data)
    except ValidationError as e:
        return [[d["type"], list(d["loc"]), d["msg"]] for d in e.errors()]
    return None

out = {"defer": T.TurnkeyBaseModel.model_config.get("defer_build"), "models": {}}
for n, data in json.load(sys.stdin).items():
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


@needs_defer
def test_same_behavior_with_defer_on_and_off():
    names = [n for i, n in enumerate(_names()) if i % SAMPLE_EVERY == 0]
    names += [n for n in HEAVY if n not in names]
    samples = {}
    for n in names:
        schema = getattr(T, n).model_json_schema(by_alias=True)
        samples[n] = _sample(schema, schema.get("$defs", {}))

    on, off = _run(_COMPARE, samples, "1"), _run(_COMPARE, samples, None)
    assert on["defer"] is True
    assert off["defer"] is None

    # Guard against the check passing because most samples were rejected.
    valid = [n for n, r in on["models"].items() if "dump" in r]
    assert len(valid) >= 0.9 * len(names), sorted(set(names) - set(valid))

    for n in names:
        assert on["models"][n] == off["models"][n], n
