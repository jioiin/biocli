"""Built-in tool: Domain-whitelisted web fetcher for bioinformatics docs.

Fetches documentation from trusted bioinformatics domains only.
Blocks arbitrary web access for security/HIPAA compliance.
"""

from __future__ import annotations

import urllib.request
import urllib.error
import re
from typing import Any
from html.parser import HTMLParser

from biopipe.core.types import PermissionLevel, Tool, ToolResult
from biopipe.core.privacy import PrivacyScrubber



# ── Whitelisted Domains ──────────────────────────────────────────────────────

ALLOWED_DOMAINS = frozenset({
    # Official tool docs
    "samtools.github.io",
    "www.htslib.org",
    "broadinstitute.github.io",
    "gatk.broadinstitute.org",
    "software.broadinstitute.org",
    # nf-core
    "nf-co.re",
    "nf-core.github.io",
    # Bioconductor
    "bioconductor.org",
    "www.bioconductor.org",
    # NCBI
    "pubmed.ncbi.nlm.nih.gov",
    "www.ncbi.nlm.nih.gov",
    "ftp.ncbi.nlm.nih.gov",
    # Genome references
    "genome.ucsc.edu",
    "www.ensembl.org",
    # General docs
    "snakemake.readthedocs.io",
    "nextflow.io",
    "www.nextflow.io",
    # Python bio libs
    "biopython.org",
    "pysam.readthedocs.io",
    # Standards
    "ga4gh.org",
    "www.ga4gh.org",
    # GitHub (for READMEs)
    "github.com",
    "raw.githubusercontent.com",
})

MAX_RESPONSE_SIZE = 200_000  # 200KB
REQUEST_TIMEOUT = 15


def is_domain_allowed(url: str) -> bool:
    """Check if URL domain is in the whitelist."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        return domain in ALLOWED_DOMAINS
    except Exception:
        return False


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML → text converter."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True
        elif tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        text = "".join(self._parts)
        # Clean up excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def fetch_url(url: str) -> dict[str, Any]:
    """Fetch content from a whitelisted URL.

    Returns dict with: content, url, content_type, size, error.
    """
    if not is_domain_allowed(url):
        from urllib.parse import urlparse
        domain = urlparse(url).hostname
        return {
            "error": (
                f"Domain '{domain}' is not in the allowed list. "
                f"BioPipe only fetches from trusted bioinformatics sources for security. "
                f"Allowed: samtools.github.io, nf-co.re, bioconductor.org, ncbi.nlm.nih.gov, etc."
            ),
            "content": "",
        }

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BioPipe-CLI/0.5 (bioinformatics AI agent)"},
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(MAX_RESPONSE_SIZE)

            if "html" in content_type:
                html_text = raw.decode("utf-8", errors="replace")
                extractor = _HTMLTextExtractor()
                extractor.feed(html_text)
                content = extractor.get_text()
            else:
                content = raw.decode("utf-8", errors="replace")

            return {
                "content": content[:MAX_RESPONSE_SIZE],
                "url": url,
                "content_type": content_type,
                "size": len(raw),
            }

    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "content": ""}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}", "content": ""}
    except Exception as e:
        return {"error": str(e), "content": ""}


# ── Tool Interface ───────────────────────────────────────────────────────────

class WebFetchTool(Tool):
    """Built-in tool: fetch documentation from trusted bioinformatics sites."""

    name = "web_fetch"
    description = (
        "Fetch documentation from trusted bioinformatics websites. "
        "Only allowed domains: samtools.github.io, nf-co.re, bioconductor.org, "
        "ncbi.nlm.nih.gov, gatk.broadinstitute.org, genome.ucsc.edu, etc. "
        "Use this to look up tool documentation, reference genome info, or paper abstracts."
    )
    parameter_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch (must be from a whitelisted bioinformatics domain)",
            },
        },
        "required": ["url"],
    }

    def required_permission(self) -> PermissionLevel:
        return PermissionLevel.READ_ONLY

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        if not isinstance(params.get("url"), str) or not params.get("url", "").strip():
            return ["url must be a non-empty string"]
        return []

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        result = fetch_url(params["url"])

        if "error" in result:
            return ToolResult(call_id="", success=False, output="", error=str(result["error"]))

        scrubber = PrivacyScrubber()
        content = scrubber.redact(result['content'])

        parts = [
            f"Source: {result['url']}",
            f"Type: {result.get('content_type', 'unknown')}",
            f"Size: {result.get('size', 0):,} bytes",
            f"\n--- Content ---\n{content}",
        ]
        return ToolResult(call_id="", success=True, output="\n".join(parts))
