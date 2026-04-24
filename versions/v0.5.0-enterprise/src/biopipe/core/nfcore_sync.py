"""NF-Core Sync Module for RAG Documentation.

Downloads or updates nf-core pipeline JSON schemas and parameters 
to index them for the LLM to write highly accurate Nextflow configurations.
"""

import urllib.request
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class NFCoreSync:
    """Syncs nf-core pipeline metadata."""

    NF_CORE_API_URL = "https://nf-co.re/pipelines.json"

    @staticmethod
    def get_pipeline_list() -> dict[str, Any]:
        """Fetch the public registry of nf-core pipelines."""
        try:
            req = urllib.request.Request(NFCoreSync.NF_CORE_API_URL)
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec
                data = json.loads(resp.read().decode("utf-8"))
            return data
        except Exception as exc:
            logger.error("Failed to sync nf-core pipelines: %s", exc)
            return {}

    @staticmethod
    def extract_documentation(pipeline_name: str) -> str:
        """Extract documentation summary for a specific nf-core workflow."""
        data = NFCoreSync.get_pipeline_list()
        
        # In a full implementation, we would query the specific pipeline's JSONSchema
        # For MVP, we just find the description
        for pipe in data.get("remote_workflows", []):
            if pipe.get("name") == pipeline_name:
                return (
                    f"nf-core/{pipeline_name}: {pipe.get('description', '')}\n"
                    f"Latest version: {pipe.get('releases', [{}])[0].get('tag_name', 'dev')}"
                )
        return f"Unknown nf-core pipeline: {pipeline_name}"
