"""Tests for memory tools - TechniqueStore + 5 memory tools."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from comfy_mcp.memory.technique_store import TechniqueStore
from comfy_mcp.tools.memory import (
    comfy_favorite_technique,
    comfy_list_techniques,
    comfy_replay_technique,
    comfy_save_technique,
    comfy_search_techniques,
)


@pytest.fixture
def mem_ctx(tmp_path):
    """Context with real TechniqueStore using tmp directory."""
    store = TechniqueStore(storage_dir=str(tmp_path))
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {
        "technique_store": store,
    }
    return ctx


SAMPLE_WORKFLOW = {
    "node_1": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
    "node_2": {"class_type": "VAEDecode", "inputs": {"samples": "1"}},
}


class TestSaveTechnique:
    @pytest.mark.asyncio
    async def test_save_technique_returns_metadata_with_id(self, mem_ctx):
        """Save returns metadata dict containing id, name, and tags."""
        result = await comfy_save_technique(SAMPLE_WORKFLOW, "my_technique", ctx=mem_ctx)
        data = json.loads(result)

        assert "id" in data
        assert data["name"] == "my_technique"
        assert "tags" in data
        assert "timestamp" in data
        assert "node_count" in data

    @pytest.mark.asyncio
    async def test_save_technique_with_description_and_tags(self, mem_ctx):
        """Save includes description and tags in returned metadata."""
        result = await comfy_save_technique(
            SAMPLE_WORKFLOW,
            "tagged_technique",
            description="A test technique",
            tags=["sdxl", "portrait"],
            ctx=mem_ctx,
        )
        data = json.loads(result)

        assert data["description"] == "A test technique"
        assert "sdxl" in data["tags"]
        assert "portrait" in data["tags"]

    @pytest.mark.asyncio
    async def test_save_technique_node_count(self, mem_ctx):
        """node_count matches number of keys in workflow."""
        result = await comfy_save_technique(SAMPLE_WORKFLOW, "count_test", ctx=mem_ctx)
        data = json.loads(result)

        assert data["node_count"] == len(SAMPLE_WORKFLOW)

    @pytest.mark.asyncio
    async def test_save_technique_default_tags_empty(self, mem_ctx):
        """Tags default to empty list when not provided."""
        result = await comfy_save_technique(SAMPLE_WORKFLOW, "notags", ctx=mem_ctx)
        data = json.loads(result)

        assert data["tags"] == []


class TestSearchTechniques:
    @pytest.mark.asyncio
    async def test_search_by_text_query(self, mem_ctx):
        """Search matches techniques by name."""
        await comfy_save_technique(SAMPLE_WORKFLOW, "portrait_workflow", ctx=mem_ctx)
        await comfy_save_technique(SAMPLE_WORKFLOW, "landscape_workflow", ctx=mem_ctx)

        result = await comfy_search_techniques(query="portrait", ctx=mem_ctx)
        data = json.loads(result)

        assert data["total_count"] == 1
        assert data["techniques"][0]["name"] == "portrait_workflow"

    @pytest.mark.asyncio
    async def test_search_by_tags(self, mem_ctx):
        """Search filters by tag membership."""
        await comfy_save_technique(SAMPLE_WORKFLOW, "tech_a", tags=["sdxl"], ctx=mem_ctx)
        await comfy_save_technique(SAMPLE_WORKFLOW, "tech_b", tags=["sd15"], ctx=mem_ctx)

        result = await comfy_search_techniques(tags=["sdxl"], ctx=mem_ctx)
        data = json.loads(result)

        assert data["total_count"] == 1
        assert data["techniques"][0]["name"] == "tech_a"

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_all(self, mem_ctx):
        """Empty query with no tags returns all techniques."""
        await comfy_save_technique(SAMPLE_WORKFLOW, "first", ctx=mem_ctx)
        await comfy_save_technique(SAMPLE_WORKFLOW, "second", ctx=mem_ctx)
        await comfy_save_technique(SAMPLE_WORKFLOW, "third", ctx=mem_ctx)

        result = await comfy_search_techniques(query="", ctx=mem_ctx)
        data = json.loads(result)

        assert data["total_count"] == 3

    @pytest.mark.asyncio
    async def test_search_by_description(self, mem_ctx):
        """Search matches text in description field."""
        await comfy_save_technique(
            SAMPLE_WORKFLOW, "gen_tech", description="generates realistic faces", ctx=mem_ctx
        )
        await comfy_save_technique(SAMPLE_WORKFLOW, "other_tech", description="landscape rendering", ctx=mem_ctx)

        result = await comfy_search_techniques(query="realistic", ctx=mem_ctx)
        data = json.loads(result)

        assert data["total_count"] == 1
        assert data["techniques"][0]["name"] == "gen_tech"

    @pytest.mark.asyncio
    async def test_search_no_match_returns_empty(self, mem_ctx):
        """Search with non-matching query returns empty list."""
        await comfy_save_technique(SAMPLE_WORKFLOW, "portrait_workflow", ctx=mem_ctx)

        result = await comfy_search_techniques(query="xxxxxxnonexistent", ctx=mem_ctx)
        data = json.loads(result)

        assert data["total_count"] == 0
        assert data["techniques"] == []


class TestListTechniques:
    @pytest.mark.asyncio
    async def test_list_techniques_returns_all(self, mem_ctx):
        """List returns all saved techniques."""
        await comfy_save_technique(SAMPLE_WORKFLOW, "a", ctx=mem_ctx)
        await comfy_save_technique(SAMPLE_WORKFLOW, "b", ctx=mem_ctx)
        await comfy_save_technique(SAMPLE_WORKFLOW, "c", ctx=mem_ctx)

        result = await comfy_list_techniques(ctx=mem_ctx)
        data = json.loads(result)

        assert data["total_count"] == 3

    @pytest.mark.asyncio
    async def test_list_techniques_respects_limit(self, mem_ctx):
        """List respects limit parameter."""
        for i in range(5):
            await comfy_save_technique(SAMPLE_WORKFLOW, f"tech_{i}", ctx=mem_ctx)

        result = await comfy_list_techniques(limit=3, ctx=mem_ctx)
        data = json.loads(result)

        assert data["total_count"] == 3
        assert len(data["techniques"]) == 3

    @pytest.mark.asyncio
    async def test_list_techniques_empty_store(self, mem_ctx):
        """List on empty store returns zero count."""
        result = await comfy_list_techniques(ctx=mem_ctx)
        data = json.loads(result)

        assert data["total_count"] == 0
        assert data["techniques"] == []

    @pytest.mark.asyncio
    async def test_list_techniques_newest_first(self, mem_ctx):
        """List returns newest techniques first."""
        for i in range(3):
            await comfy_save_technique(SAMPLE_WORKFLOW, f"tech_{i}", ctx=mem_ctx)
            time.sleep(0.01)

        result = await comfy_list_techniques(ctx=mem_ctx)
        data = json.loads(result)

        names = [t["name"] for t in data["techniques"]]
        assert names[0] == "tech_2"
        assert names[-1] == "tech_0"


class TestReplayTechnique:
    @pytest.mark.asyncio
    async def test_replay_technique_returns_workflow_data(self, mem_ctx):
        """Replay returns the full technique including workflow."""
        save_result = await comfy_save_technique(SAMPLE_WORKFLOW, "replay_test", ctx=mem_ctx)
        save_data = json.loads(save_result)
        tech_id = save_data["id"]

        result = await comfy_replay_technique(tech_id, ctx=mem_ctx)
        data = json.loads(result)

        assert "workflow" in data
        assert data["workflow"] == SAMPLE_WORKFLOW
        assert data["name"] == "replay_test"

    @pytest.mark.asyncio
    async def test_replay_technique_increments_use_count(self, mem_ctx):
        """Replay increments use_count each time it is called."""
        save_result = await comfy_save_technique(SAMPLE_WORKFLOW, "use_count_test", ctx=mem_ctx)
        save_data = json.loads(save_result)
        tech_id = save_data["id"]

        result1 = await comfy_replay_technique(tech_id, ctx=mem_ctx)
        data1 = json.loads(result1)
        assert data1["use_count"] == 1

        result2 = await comfy_replay_technique(tech_id, ctx=mem_ctx)
        data2 = json.loads(result2)
        assert data2["use_count"] == 2

    @pytest.mark.asyncio
    async def test_replay_technique_nonexistent_returns_error(self, mem_ctx):
        """Replay with unknown ID returns error dict."""
        result = await comfy_replay_technique("nonexistent_id", ctx=mem_ctx)
        data = json.loads(result)

        assert "error" in data
        assert data["technique_id"] == "nonexistent_id"


class TestFavoriteTechnique:
    @pytest.mark.asyncio
    async def test_favorite_technique_sets_favorite_and_rating(self, mem_ctx):
        """Favorite sets both favorite flag and rating."""
        save_result = await comfy_save_technique(SAMPLE_WORKFLOW, "fav_test", ctx=mem_ctx)
        save_data = json.loads(save_result)
        tech_id = save_data["id"]

        result = await comfy_favorite_technique(tech_id, favorite=True, rating=5, ctx=mem_ctx)
        data = json.loads(result)

        assert data["favorite"] is True
        assert data["rating"] == 5
        assert data["id"] == tech_id

    @pytest.mark.asyncio
    async def test_favorite_technique_unfavorite(self, mem_ctx):
        """Favorite can be set to False to unfavorite."""
        save_result = await comfy_save_technique(SAMPLE_WORKFLOW, "unfav_test", ctx=mem_ctx)
        save_data = json.loads(save_result)
        tech_id = save_data["id"]

        await comfy_favorite_technique(tech_id, favorite=True, ctx=mem_ctx)
        result = await comfy_favorite_technique(tech_id, favorite=False, ctx=mem_ctx)
        data = json.loads(result)

        assert data["favorite"] is False

    @pytest.mark.asyncio
    async def test_favorite_technique_nonexistent_returns_error(self, mem_ctx):
        """Favorite with unknown ID returns error dict."""
        result = await comfy_favorite_technique("nonexistent_id", ctx=mem_ctx)
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_favorite_technique_rating_capped_at_5(self, mem_ctx):
        """Rating values above 5 are capped at 5."""
        save_result = await comfy_save_technique(SAMPLE_WORKFLOW, "cap_test", ctx=mem_ctx)
        save_data = json.loads(save_result)
        tech_id = save_data["id"]

        result = await comfy_favorite_technique(tech_id, rating=99, ctx=mem_ctx)
        data = json.loads(result)

        assert data["rating"] == 5


class TestPersistence:
    @pytest.mark.asyncio
    async def test_technique_survives_new_store_instance(self, tmp_path):
        """Technique persisted to disk is loaded by a new TechniqueStore instance."""
        store1 = TechniqueStore(storage_dir=str(tmp_path))
        ctx1 = MagicMock()
        ctx1.request_context.lifespan_context = {"technique_store": store1}

        save_result = await comfy_save_technique(SAMPLE_WORKFLOW, "persisted_tech", ctx=ctx1)
        save_data = json.loads(save_result)
        tech_id = save_data["id"]

        # New store instance pointing to same directory
        store2 = TechniqueStore(storage_dir=str(tmp_path))
        ctx2 = MagicMock()
        ctx2.request_context.lifespan_context = {"technique_store": store2}

        result = await comfy_replay_technique(tech_id, ctx=ctx2)
        data = json.loads(result)

        assert "error" not in data
        assert data["name"] == "persisted_tech"
        assert data["workflow"] == SAMPLE_WORKFLOW


class TestDeleteTechnique:
    @pytest.mark.asyncio
    async def test_delete_technique_removes_from_list(self, mem_ctx):
        """Deleted technique no longer appears in list."""
        save_result = await comfy_save_technique(SAMPLE_WORKFLOW, "to_delete", ctx=mem_ctx)
        save_data = json.loads(save_result)
        tech_id = save_data["id"]

        store = mem_ctx.request_context.lifespan_context["technique_store"]
        deleted = store.delete(tech_id)

        assert deleted is True

        result = await comfy_list_techniques(ctx=mem_ctx)
        data = json.loads(result)
        ids = [t["id"] for t in data["techniques"]]
        assert tech_id not in ids

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, mem_ctx):
        """Deleting a non-existent technique returns False."""
        store = mem_ctx.request_context.lifespan_context["technique_store"]
        result = store.delete("nonexistent_id")
        assert result is False


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_full_roundtrip_save_search_replay(self, mem_ctx):
        """Full round-trip: save -> search -> replay -> verify workflow matches."""
        original_workflow = {
            "node_1": {"class_type": "KSampler", "inputs": {"seed": 99, "steps": 30}},
            "node_2": {"class_type": "VAEDecode", "inputs": {"samples": "link"}},
            "node_3": {"class_type": "SaveImage", "inputs": {"filename_prefix": "output"}},
        }

        # Save
        save_result = await comfy_save_technique(
            original_workflow, "roundtrip_tech", description="roundtrip test", tags=["test"], ctx=mem_ctx
        )
        save_data = json.loads(save_result)
        tech_id = save_data["id"]

        # Search
        search_result = await comfy_search_techniques(query="roundtrip", ctx=mem_ctx)
        search_data = json.loads(search_result)
        assert search_data["total_count"] == 1
        assert search_data["techniques"][0]["id"] == tech_id

        # Replay
        replay_result = await comfy_replay_technique(tech_id, ctx=mem_ctx)
        replay_data = json.loads(replay_result)

        # Verify workflow matches exactly
        assert replay_data["workflow"] == original_workflow
        assert replay_data["name"] == "roundtrip_tech"
        assert "test" in replay_data["tags"]
        assert replay_data["use_count"] == 1


class TestTechniqueMetadata:
    @pytest.mark.asyncio
    async def test_save_technique_includes_metadata(self, mem_ctx):
        """Saved techniques should include node classes and model references."""
        workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl.safetensors"}},
            "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0]}},
        }
        result_str = await comfy_save_technique(
            name="test_technique",
            workflow=workflow,
            tags=["test"],
            ctx=mem_ctx,
        )

        # Parse the result and check metadata
        data = json.loads(result_str)
        assert "node_classes" in data
        assert "CheckpointLoaderSimple" in data["node_classes"]
        assert "KSampler" in data["node_classes"]
        assert "model_references" in data
        assert "sdxl.safetensors" in data["model_references"]
