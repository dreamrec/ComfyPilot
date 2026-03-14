"""Tests for DocsIndex — documentation lookup and search."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def populated_store(tmp_path):
    """DocsStore with some cached docs."""
    from comfy_mcp.docs.store import DocsStore
    store = DocsStore(storage_dir=str(tmp_path / "docs"))
    store.save_embedded("KSampler", "# KSampler\nSamples latent noise using various methods.\nUses model, seed, steps, cfg, sampler_name.")
    store.save_embedded("SaveImage", "# SaveImage\nSaves generated images to the output directory.")
    store.save_embedded("CheckpointLoaderSimple", "# CheckpointLoaderSimple\nLoads a diffusion model checkpoint.\nOutputs MODEL, CLIP, VAE.")
    store.save_llms("# Getting Started\nIntro guide.\n\n## Sampling\nHow sampling works in ComfyUI.\n\n## Models\nAbout model loading.")
    return store


class TestDocsIndexLookup:
    def test_get_node_doc_returns_cached(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        result = index.get_node_doc("KSampler")
        assert result is not None
        assert "Samples latent noise" in result["description"]

    def test_get_node_doc_returns_none_for_missing(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        result = index.get_node_doc("FakeNode")
        assert result is None

    def test_get_node_doc_merges_object_info(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        object_info = {
            "KSampler": {
                "input": {"required": {"seed": ["INT"], "steps": ["INT"]}},
                "output": ["LATENT"],
            }
        }
        index = DocsIndex(populated_store, object_info=object_info)
        result = index.get_node_doc("KSampler")
        assert "schema" in result
        assert result["schema"]["output"] == ["LATENT"]


class TestDocsIndexSearch:
    def test_search_finds_by_keyword(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        results = index.search("sampl")
        assert len(results) >= 1
        assert any("KSampler" in r["class_name"] for r in results)

    def test_search_returns_empty_for_no_match(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        results = index.search("quantum_physics")
        assert results == []

    def test_search_respects_limit(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        results = index.search("", limit=1)
        assert len(results) <= 1


class TestDocsIndexGuide:
    def test_get_guide_finds_section(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        result = index.get_guide("sampling")
        assert result is not None
        assert "How sampling works" in result["content"]

    def test_get_guide_returns_none_for_unknown(self, populated_store):
        from comfy_mcp.docs.index import DocsIndex
        index = DocsIndex(populated_store)
        result = index.get_guide("quantum_computing")
        assert result is None
