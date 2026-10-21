"""EUR-Lex and CELLAR regulatory document ingestion.

The importer requests the official Formex ZIP for a CELEX work from the
Publications Office CELLAR API, checks the CELEX and language, and stores a
versioned local copy. Consolidated texts and later amending acts are recorded
as references and are not merged into the requested instrument.
"""

from ai_governance.ingestion.service import import_celex

__all__ = ["import_celex"]
