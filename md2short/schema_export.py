"""`RemotionProps` JSON Schema 출력 (Remotion TS 타입 생성 입력)."""

from __future__ import annotations

import json
import sys

from md2short.schema import RemotionProps


def _strip_property_titles(node: object) -> None:
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for value in props.values():
                if isinstance(value, dict):
                    value.pop("title", None)
        for value in node.values():
            _strip_property_titles(value)
    elif isinstance(node, list):
        for value in node:
            _strip_property_titles(value)


def props_json_schema() -> str:
    schema = RemotionProps.model_json_schema(by_alias=True, mode="serialization")
    _strip_property_titles(schema)
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    sys.stdout.write(props_json_schema())
