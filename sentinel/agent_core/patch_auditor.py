"""Patch auditing utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PatchProposal:
    target_file: str
    patch_text: str
    rationale: str


class PatchRejected(Exception):
    pass


class PatchAuditor:
    """Static checks for potentially unsafe patches."""

    banned_tokens = (
        "os.system",
        "subprocess",
        "shutil.rmtree",
        "rm -rf",
        "unlink('/')",
    )

    def audit(self, proposal: PatchProposal) -> None:
        failures: List[str] = []
        for token in self.banned_tokens:
            if token in proposal.patch_text:
                failures.append(token)
        if proposal.target_file.startswith("/"):
            failures.append("absolute-path")

        if failures:
            logger.error("Patch rejected due to: %s", ", ".join(failures))
            raise PatchRejected(
                f"Patch contains unsafe constructs: {', '.join(failures)}"
            )
        logger.info("Patch accepted for %s", proposal.target_file)
