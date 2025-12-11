"""Self-modification engine for Sentinel MAX."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sentinel.agent_core.patch_auditor import PatchAuditor, PatchProposal, PatchRejected
from sentinel.logging.logger import get_logger

logger = get_logger(__name__)


class SelfModificationEngine:
    def __init__(self, auditor: PatchAuditor) -> None:
        self.auditor = auditor

    def propose_patch(self, file_path: str, new_content: str, rationale: str) -> Optional[PatchProposal]:
        proposal = PatchProposal(target_file=file_path, patch_text=new_content, rationale=rationale)
        try:
            self.auditor.audit(proposal)
        except PatchRejected:
            return None
        return proposal

    def apply_patch(self, proposal: PatchProposal) -> bool:
        try:
            self.auditor.audit(proposal)
        except PatchRejected:
            return False

        path = Path(proposal.target_file)
        path.write_text(proposal.patch_text)
        logger.info("Patch applied to %s", proposal.target_file)
        return True
