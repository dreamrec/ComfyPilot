"""RegistryResolver -- maps missing nodes to registry packages.

Uses the RegistryIndex cache first, falls back to API lookups.
Deduplicates results (multiple nodes from same package = one install).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("comfypilot.registry")


class RegistryResolver:
    """Resolves missing node class names to registry packages."""

    def __init__(self, client, index, snapshot: dict[str, Any]):
        self._client = client
        self._index = index
        self._snapshot = snapshot

    async def resolve_one(self, class_name: str) -> dict[str, Any]:
        """Resolve a single node class name to a package.

        Returns: {"class": str, "package": str|None, "latest_version": str|None,
                  "compatible": bool, "install_cmd": str|None, "note": str|None}
        """
        # Check cache first
        cached = self._index.lookup(class_name)
        if cached is not None:
            if cached.get("package") is None:
                return {
                    "class": class_name,
                    "package": None,
                    "latest_version": None,
                    "compatible": False,
                    "install_cmd": None,
                    "note": "Not found in registry — may be a local/private custom node",
                }
            return self._build_result(class_name, cached["package"], cached.get("version"))

        # API lookup
        api_result = await self._client.reverse_lookup(class_name)
        if api_result is None:
            self._index.cache_negative(class_name)
            return {
                "class": class_name,
                "package": None,
                "latest_version": None,
                "compatible": False,
                "install_cmd": None,
                "note": "Not found in registry — may be a local/private custom node",
            }

        # Extract package info
        node_info = api_result.get("node", {})
        package_id = node_info.get("id", "")
        latest = node_info.get("latest_version", {})
        version = latest.get("version", "unknown")

        self._index.cache_positive(class_name, package_id, version)
        return self._build_result(class_name, package_id, version)

    def _build_result(self, class_name: str, package_id: str, version: str | None) -> dict[str, Any]:
        """Build a resolution result with compatibility info."""
        return {
            "class": class_name,
            "package": package_id,
            "latest_version": version,
            "compatible": True,  # TODO: full compat check against snapshot in future
            "install_cmd": f"comfy node install {package_id}",
            "note": None,
        }

    async def resolve_batch(self, class_names: list[str]) -> dict[str, Any]:
        """Resolve multiple missing node classes, deduplicating by package.

        Uses bulk_resolve API when 3+ uncached class names need resolution
        (per spec: prefer bulk resolve for 3+ nodes).
        """
        results = []
        packages_seen: dict[str, list[str]] = {}  # package_id -> [class_names]

        # Split into cached and uncached
        uncached = []
        for name in class_names:
            cached = self._index.lookup(name)
            if cached is not None:
                if cached.get("package") is None:
                    results.append({
                        "class": name, "package": None, "latest_version": None,
                        "compatible": False, "install_cmd": None,
                        "note": "Not found in registry — may be a local/private custom node",
                    })
                else:
                    results.append(self._build_result(name, cached["package"], cached.get("version")))
            else:
                uncached.append(name)

        # Use bulk resolve API for 3+ uncached nodes
        if len(uncached) >= 3:
            bulk_result = await self._client.bulk_resolve(
                [{"node_class": n} for n in uncached]
            )
            for name in uncached:
                entry = bulk_result.get(name)
                if entry and entry.get("node"):
                    node_info = entry["node"]
                    pkg_id = node_info.get("id", "")
                    version = node_info.get("latest_version", {}).get("version", "unknown")
                    self._index.cache_positive(name, pkg_id, version)
                    results.append(self._build_result(name, pkg_id, version))
                else:
                    self._index.cache_negative(name)
                    results.append({
                        "class": name, "package": None, "latest_version": None,
                        "compatible": False, "install_cmd": None,
                        "note": "Not found in registry — may be a local/private custom node",
                    })
        else:
            for name in uncached:
                result = await self.resolve_one(name)
                results.append(result)

        # Build packages_seen from all results
        for result in results:
            pkg = result.get("package")
            if pkg:
                if pkg not in packages_seen:
                    packages_seen[pkg] = []
                packages_seen[pkg].append(result["class"])

        # Add deduplication notes
        for result in results:
            pkg = result.get("package")
            if pkg and len(packages_seen.get(pkg, [])) > 1:
                others = [n for n in packages_seen[pkg] if n != result["class"]]
                if others:
                    result["note"] = f"Same package as {', '.join(others)}"

        # Save index after batch
        self._index.save()

        resolved = sum(1 for r in results if r.get("package") is not None)
        unresolved = len(results) - resolved
        unique_packages = len(packages_seen)

        n = unique_packages
        m = resolved
        resolution = f"Install {n} package{'s' if n != 1 else ''} to resolve all {m} missing node{'s' if m != 1 else ''}"
        if unresolved > 0:
            resolution += f". {unresolved} node{'s' if unresolved != 1 else ''} not found in registry."

        return {
            "nodes": results,
            "resolved": resolved,
            "unresolved": unresolved,
            "unique_packages": unique_packages,
            "resolution": resolution,
        }
