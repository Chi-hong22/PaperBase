"""Terminology Library 单元测试"""

import pytest
from pathlib import Path
from paperbase.core.terminology import (
    load_terminology,
    fuzzy_match,
    normalize_entities,
)


@pytest.fixture
def sample_terminology():
    """Sample terminology for testing"""
    return {
        "aliases": {
            "methods": {
                "submap": ["submapping", "sub-map", "local map", "local mapping"],
                "loop_closure": ["loop detection", "place recognition", "loop closing"],
                "SLAM": ["slam", "Simultaneous Localization and Mapping"],
            },
            "platforms": {
                "AUV": ["autonomous underwater vehicle", "underwater robot", "underwater vehicle"],
                "UAV": ["drone", "unmanned aerial vehicle"],
            },
            "datasets": {
                "KITTI": ["kitti", "Kitti"],
            },
            "domains": {
                "underwater navigation": ["underwater SLAM", "subsea navigation"],
            },
            "constraints": {
                "real-time": ["real time", "realtime", "online"],
            },
        }
    }


def test_load_terminology_from_yaml(tmp_path):
    """Test loading terminology from YAML file"""
    # Create test YAML
    yaml_content = """
aliases:
  methods:
    submap:
      - submapping
      - sub-map
  platforms:
    AUV:
      - autonomous underwater vehicle
"""
    yaml_file = tmp_path / "terminology.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    # Load
    terminology = load_terminology(yaml_file)

    # Verify structure
    assert "aliases" in terminology
    assert "methods" in terminology["aliases"]
    assert "submap" in terminology["aliases"]["methods"]
    assert "submapping" in terminology["aliases"]["methods"]["submap"]


def test_load_terminology_missing_file():
    """Test loading non-existent file returns empty structure"""
    non_existent = Path("F:/non_existent_file.yaml")
    terminology = load_terminology(non_existent)

    # Should return empty but valid structure
    assert terminology == {"aliases": {}}


def test_fuzzy_match_exact_canonical(sample_terminology):
    """Test exact match on canonical term"""
    result = fuzzy_match("submap", "methods", sample_terminology)
    assert result == "submap"


def test_fuzzy_match_variant(sample_terminology):
    """Test matching a variant to canonical term"""
    result = fuzzy_match("submapping", "methods", sample_terminology)
    assert result == "submap"

    result = fuzzy_match("sub-map", "methods", sample_terminology)
    assert result == "submap"

    result = fuzzy_match("local map", "methods", sample_terminology)
    assert result == "submap"


def test_fuzzy_match_case_insensitive(sample_terminology):
    """Test case-insensitive matching"""
    # Canonical term with different case
    result = fuzzy_match("SUBMAP", "methods", sample_terminology)
    assert result == "submap"

    result = fuzzy_match("SubMap", "methods", sample_terminology)
    assert result == "submap"

    # Variant with different case
    result = fuzzy_match("SUBMAPPING", "methods", sample_terminology)
    assert result == "submap"

    result = fuzzy_match("Loop Detection", "methods", sample_terminology)
    assert result == "loop_closure"


def test_fuzzy_match_no_match(sample_terminology):
    """Test no match returns None"""
    result = fuzzy_match("unknown_method", "methods", sample_terminology)
    assert result is None

    result = fuzzy_match("random_term", "platforms", sample_terminology)
    assert result is None


def test_fuzzy_match_wrong_category(sample_terminology):
    """Test searching in wrong category returns None"""
    # "AUV" exists in platforms, not in methods
    result = fuzzy_match("AUV", "methods", sample_terminology)
    assert result is None


def test_fuzzy_match_missing_category(sample_terminology):
    """Test searching in non-existent category returns None"""
    result = fuzzy_match("anything", "non_existent_category", sample_terminology)
    assert result is None


def test_normalize_entities_methods(sample_terminology):
    """Test normalizing method entities"""
    entities = {
        "methods": [
            {"name": "submapping", "type": "mapping"},
            {"name": "loop detection", "type": "localization"},
            {"name": "unknown_method", "type": "other"},
        ]
    }

    normalized = normalize_entities(entities, sample_terminology)

    # Check normalization
    assert normalized["methods"][0]["name"] == "submap"
    assert normalized["methods"][0]["type"] == "mapping"

    assert normalized["methods"][1]["name"] == "loop_closure"
    assert normalized["methods"][1]["type"] == "localization"

    # Unknown terms remain unchanged
    assert normalized["methods"][2]["name"] == "unknown_method"


def test_normalize_entities_all_categories(sample_terminology):
    """Test normalizing all entity categories"""
    entities = {
        "methods": [{"name": "sub-map"}],
        "platforms": [{"name": "drone"}],
        "datasets": [{"name": "kitti"}],
        "domains": [{"name": "underwater SLAM"}],
        "constraints": [{"name": "real time"}],
    }

    normalized = normalize_entities(entities, sample_terminology)

    assert normalized["methods"][0]["name"] == "submap"
    assert normalized["platforms"][0]["name"] == "UAV"
    assert normalized["datasets"][0]["name"] == "KITTI"
    assert normalized["domains"][0]["name"] == "underwater navigation"
    assert normalized["constraints"][0]["name"] == "real-time"


def test_normalize_entities_empty_categories(sample_terminology):
    """Test normalizing with missing or empty categories"""
    entities = {
        "methods": [],
        "platforms": [{"name": "AUV"}],
    }

    normalized = normalize_entities(entities, sample_terminology)

    # Empty lists remain empty
    assert normalized["methods"] == []

    # Existing categories are processed
    assert normalized["platforms"][0]["name"] == "AUV"  # Already canonical


def test_normalize_entities_preserves_extra_fields(sample_terminology):
    """Test that normalization preserves extra fields"""
    entities = {
        "methods": [
            {
                "name": "submapping",
                "type": "mapping",
                "confidence": 0.95,
                "extra_field": "preserved",
            }
        ]
    }

    normalized = normalize_entities(entities, sample_terminology)

    assert normalized["methods"][0]["name"] == "submap"
    assert normalized["methods"][0]["type"] == "mapping"
    assert normalized["methods"][0]["confidence"] == 0.95
    assert normalized["methods"][0]["extra_field"] == "preserved"


def test_normalize_entities_case_insensitive(sample_terminology):
    """Test normalization is case-insensitive"""
    entities = {
        "methods": [{"name": "SUBMAPPING"}],
        "platforms": [{"name": "Autonomous Underwater Vehicle"}],
    }

    normalized = normalize_entities(entities, sample_terminology)

    assert normalized["methods"][0]["name"] == "submap"
    assert normalized["platforms"][0]["name"] == "AUV"


def test_normalize_entities_empty_input(sample_terminology):
    """Test normalizing empty entity dict"""
    entities = {}
    normalized = normalize_entities(entities, sample_terminology)
    assert normalized == {}


def test_normalize_entities_no_terminology():
    """Test normalization with empty terminology"""
    entities = {
        "methods": [{"name": "submap"}],
    }
    empty_terminology = {"aliases": {}}

    normalized = normalize_entities(entities, empty_terminology)

    # All terms remain unchanged
    assert normalized["methods"][0]["name"] == "submap"
