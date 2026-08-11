from __future__ import annotations

from types import SimpleNamespace

from scripts import live_smoke


def test_geometrypack_fixture_uses_flat_dynamic_combo_and_unique_output() -> None:
    workflow = live_smoke.make_geometrypack_workflow("smoke_object")

    assert workflow["3"]["inputs"]["operation"] == "translate"
    assert workflow["3"]["inputs"]["operation.translate_z"] == 1.25
    assert not isinstance(workflow["3"]["inputs"]["operation"], dict)
    assert workflow["6"]["inputs"] == {
        "mesh_a": ["1", 0],
        "mesh_b": ["3", 0],
        "mesh_c": ["5", 0],
    }
    assert workflow["7"]["inputs"] == {
        "trimesh": ["6", 0],
        "file_path": "smoke_object",
        "format": "glb",
    }


def test_unique_output_name_is_path_safe() -> None:
    name = live_smoke.make_unique_output_name("../unsafe prefix\\nested")

    assert name.startswith("unsafe_prefix_nested_")
    assert "/" not in name
    assert "\\" not in name
    assert ".." not in name


def test_decode_tool_result_prefers_json_text_over_structured_wrapper() -> None:
    result = SimpleNamespace(
        isError=False,
        content=[SimpleNamespace(text='{"status":"ok","count":3}')],
        structuredContent={"result": '{"status":"stale"}'},
    )

    assert live_smoke.decode_tool_result(result, "example") == {
        "status": "ok",
        "count": 3,
    }


def test_terminal_history_state_distinguishes_success_failure_and_pending() -> None:
    assert live_smoke._terminal_history_state({"error": "not found"}) == (
        False,
        False,
        "not found",
    )
    assert live_smoke._terminal_history_state(
        {"status": {"status_str": "success", "completed": True}}
    ) == (True, True, "success")
    assert live_smoke._terminal_history_state(
        {"status": {"status_str": "error", "completed": True}}
    ) == (True, False, "error")
