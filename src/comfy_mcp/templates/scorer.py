"""TemplateScorer -- relevance ranking for template search.

Scores templates based on tag match, category match, model compatibility,
and node compatibility. Uses source precedence as tiebreaker.
"""

from __future__ import annotations

from typing import Any

# Scoring weights (hardcoded defaults, defined as constants for tuning)
TAG_WEIGHT = 0.3
CATEGORY_WEIGHT = 0.2
MODEL_WEIGHT = 0.3
NODE_WEIGHT = 0.2

# Source precedence for tiebreaking (lower = higher priority)
SOURCE_PRECEDENCE = {"official": 0, "custom_node": 1, "builtin": 2}


class TemplateScorer:
    """Ranks templates by relevance to a query and installed environment."""

    def __init__(self, installed_nodes: set[str], installed_models: dict[str, list[str]]):
        self._nodes = installed_nodes
        self._models = installed_models

    def score(
        self,
        query: str,
        templates: list[dict[str, Any]],
        tags: list[str] | None = None,
        category: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Score and rank templates. Returns scored results with warnings."""
        query_tokens = set(query.lower().split()) if query else set()
        filter_tags = set(t.lower() for t in tags) if tags else set()

        scored = []
        for t in templates:
            template_tags = set(tag.lower() for tag in t.get("tags", []))
            template_cat = t.get("category", "").lower()

            # Tag overlap
            if query_tokens:
                tag_overlap = len(query_tokens & template_tags) / max(len(query_tokens), 1)
                # Also check name and description
                name_match = any(tok in t.get("name", "").lower() for tok in query_tokens)
                desc_match = any(tok in t.get("description", "").lower() for tok in query_tokens)
                if name_match or desc_match:
                    tag_overlap = max(tag_overlap, 0.5)
            else:
                tag_overlap = 1.0  # no query = everything matches

            # Filter tag match
            if filter_tags and not (filter_tags & template_tags):
                continue

            # Category match
            cat_match = 1.0 if (category and category.lower() == template_cat) else (0.5 if not category else 0.0)

            # Node compatibility
            required_nodes = t.get("required_nodes", [])
            warnings = []
            if required_nodes:
                available = sum(1 for n in required_nodes if n in self._nodes)
                node_ratio = available / len(required_nodes)
                missing = [n for n in required_nodes if n not in self._nodes]
                if missing:
                    warnings.append(f"Missing nodes: {', '.join(missing)}")
            else:
                node_ratio = 1.0

            # Model compatibility
            required_models = t.get("required_models", {})
            if required_models:
                model_available = 0
                model_total = 0
                for folder, count in required_models.items():
                    model_total += count
                    if len(self._models.get(folder, [])) >= count:
                        model_available += count
                    else:
                        warnings.append(f"Need {count} {folder} model(s), have {len(self._models.get(folder, []))}")
                model_ratio = model_available / max(model_total, 1)
            else:
                model_ratio = 1.0

            # Compute score
            total = (TAG_WEIGHT * tag_overlap
                     + CATEGORY_WEIGHT * cat_match
                     + MODEL_WEIGHT * model_ratio
                     + NODE_WEIGHT * node_ratio)

            scored.append({
                "id": t.get("id", t.get("name", "")),
                "name": t.get("name", ""),
                "category": t.get("category", ""),
                "source": t.get("source", "unknown"),
                "description": t.get("description", ""),
                "score": round(total, 3),
                "warnings": warnings,
            })

        # Sort by score desc, then source precedence asc
        scored.sort(key=lambda x: (-x["score"], SOURCE_PRECEDENCE.get(x["source"], 9)))
        return scored[:limit]
