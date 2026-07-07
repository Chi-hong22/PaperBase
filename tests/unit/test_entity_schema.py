"""Paper Schema 实体字段测试"""

import pytest
from pydantic import ValidationError
from paperbase.schemas.paper import PaperMetadata, PaperEntity


def test_paper_entity_minimal():
    """Test PaperEntity with minimal fields"""
    entity = PaperEntity(name="SLAM")
    assert entity.name == "SLAM"
    assert entity.type is None
    assert entity.confidence is None


def test_paper_entity_with_type():
    """Test PaperEntity with type"""
    entity = PaperEntity(name="submap", type="mapping")
    assert entity.name == "submap"
    assert entity.type == "mapping"


def test_paper_entity_with_confidence():
    """Test PaperEntity with confidence"""
    entity = PaperEntity(name="Transformer", confidence=0.95)
    assert entity.name == "Transformer"
    assert entity.confidence == 0.95


def test_paper_entity_invalid_confidence():
    """Test PaperEntity rejects invalid confidence"""
    with pytest.raises(ValidationError, match="confidence 必须在 0-1 范围内"):
        PaperEntity(name="BERT", confidence=1.5)

    with pytest.raises(ValidationError, match="confidence 必须在 0-1 范围内"):
        PaperEntity(name="BERT", confidence=-0.1)


def test_paper_metadata_with_entities():
    """Test PaperMetadata with entities field"""
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="doi:10.1234/test",
        storage_id="p_test001",
        title="Test Paper",
        authors=[{"name": "John Doe"}],
        year=2024,
        abstract="Test abstract",
        entities={
            "methods": [
                {"name": "SLAM"},
                {"name": "Particle Filter", "type": "localization"}
            ],
            "datasets": [
                {"name": "AQUALOC"}
            ],
            "domains": [
                {"name": "AUV navigation"}
            ]
        }
    )

    assert "entities" in metadata.model_dump()
    assert len(metadata.entities["methods"]) == 2
    assert metadata.entities["methods"][0].name == "SLAM"
    assert metadata.entities["datasets"][0].name == "AQUALOC"


def test_paper_metadata_without_entities():
    """Test PaperMetadata with default empty entities"""
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="doi:10.1234/test",
        storage_id="p_test001",
        title="Test Paper",
        authors=[{"name": "John Doe"}],
        year=2024,
        abstract="Test abstract"
    )

    assert metadata.entities == {}


def test_paper_metadata_empty_entity_list():
    """Test PaperMetadata with empty entity list"""
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="doi:10.1234/test",
        storage_id="p_test001",
        title="Test Paper",
        authors=[{"name": "John Doe"}],
        year=2024,
        abstract="Test abstract",
        entities={
            "methods": [],
            "datasets": []
        }
    )

    assert metadata.entities["methods"] == []
    assert metadata.entities["datasets"] == []


def test_paper_metadata_unknown_entity_category():
    """Test PaperMetadata accepts unknown entity categories"""
    # 允许自定义类别（为未来扩展留空间）
    metadata = PaperMetadata(
        schema_version="1.0",
        paper_id="doi:10.1234/test",
        storage_id="p_test001",
        title="Test Paper",
        authors=[{"name": "John Doe"}],
        year=2024,
        abstract="Test abstract",
        entities={
            "methods": [{"name": "SLAM"}],
            "custom_category": [{"name": "Custom Entity"}]
        }
    )

    assert "custom_category" in metadata.entities
    assert metadata.entities["custom_category"][0].name == "Custom Entity"
