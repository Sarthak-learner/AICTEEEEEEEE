"""Load and validate YAML rule definitions from the rulebook directory."""
import hashlib
import json
import yaml
from pathlib import Path
from typing import Any
import jsonschema

# JSON Schema for rule validation
RULE_SCHEMA = {
    "type": "object",
    "required": ["rule_key", "title", "severity", "inputs", "check"],
    "properties": {
        "rule_key": {"type": "string"},
        "title": {"type": "string"},
        "clause_ref": {"type": "string"},
        "source_page": {"type": "string"},
        "verified": {"type": "boolean"},
        "severity": {"enum": ["CRITICAL", "MAJOR", "MINOR", "ADVISORY"]},
        "applicability": {"type": "object"},
        "inputs": {"type": "object"},
        "check": {
            "type": "object",
            "required": ["fn", "params"],
            "properties": {
                "fn": {"type": "string"},
                "params": {"type": "object"},
            }
        },
        "explain": {"type": "string"},
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["inputs", "expect"],
            }
        },
        "override": {"type": "object"},
    }
}


def load_rulebook_from_dir(directory: Path) -> tuple[list[dict], str]:
    """Load all YAML rules from a directory. Returns (rules, content_sha256)."""
    rules = []
    content_parts = []
    for yaml_file in sorted(directory.glob("*.yaml")):
        with open(yaml_file, "r", encoding="utf-8") as f:
            text = f.read()
            content_parts.append(text)
            rule = yaml.safe_load(text)
            try:
                jsonschema.validate(rule, RULE_SCHEMA)
            except jsonschema.ValidationError as e:
                raise ValueError(f"Rule validation failed in {yaml_file}: {e.message}")
            rules.append(rule)
    content_sha256 = hashlib.sha256("\n".join(content_parts).encode()).hexdigest()
    return rules, content_sha256


def load_rule_from_yaml(path: Path) -> dict:
    """Load a single YAML rule and validate it."""
    with open(path, "r", encoding="utf-8") as f:
        rule = yaml.safe_load(f)
    jsonschema.validate(rule, RULE_SCHEMA)
    return rule
