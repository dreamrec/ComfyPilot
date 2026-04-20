"""Normalized schema models for ComfyUI object_info (handles V1 and V3)."""
from comfy_mcp.schemas.node_schema import InputSpec, NodeSchema, OutputSpec, parse_object_info

__all__ = ["InputSpec", "NodeSchema", "OutputSpec", "parse_object_info"]
