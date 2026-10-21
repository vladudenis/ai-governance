"""Content-addressed store for imported regulatory versions.

The same ZIP bytes produce one catalog row and one pair of files. A later
import with different bytes writes a new pair and marks the previous row
superseded. Older files stay on disk so a historical assessment can still
cite the version it used.
"""

import hashlib
import re
from pathlib import Path

from ai_governance.ingestion.models import Catalog, ImportResult, RegulatoryVersion, StoredVersion

_CELEX_PATH = re.compile(r"^[0-9A-Z][0-9A-Z-]{4,63}$")


class RegulatoryStore:
    """JSON catalog plus one directory per CELEX, language, and document kind."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.catalog_path = self.root / "index.json"

    def import_document(self, document: RegulatoryVersion, raw_zip: bytes) -> ImportResult:
        """Store ``document`` unless this exact ZIP is already catalogued."""
        digest = hashlib.sha256(raw_zip).hexdigest()
        if digest != document.content_sha256:
            raise ValueError("Regulatory version hash does not match the Formex ZIP")
        if not _CELEX_PATH.match(document.celex):
            raise ValueError(f"CELEX {document.celex} cannot be used as a storage path")

        catalog = self._read_catalog()
        existing = self._find(catalog, document)
        if existing is not None:
            return ImportResult(created=False, version=existing)

        for version in catalog.versions:
            if _same_work(version, document) and not version.superseded:
                version.superseded = True

        relative = (
            Path(document.celex)
            / document.language
            / document.document_kind.value
            / document.content_sha256
        )
        json_path = self.root / relative.with_suffix(".json")
        zip_path = self.root / relative.with_suffix(".zip")
        stored = StoredVersion(
            celex=document.celex,
            language=document.language,
            document_kind=document.document_kind,
            content_sha256=document.content_sha256,
            retrieved_at=document.retrieved_at,
            relative_path=relative.with_suffix(".json").as_posix(),
            superseded=False,
            title=document.title,
            manifestation_uri=document.manifestation_uri,
        )
        catalog.versions.append(stored)
        _write_bytes(zip_path, raw_zip)
        _write_text(json_path, document.model_dump_json(indent=2))
        self._write_catalog(catalog)
        return ImportResult(created=True, version=stored)

    def load(self, version: StoredVersion) -> RegulatoryVersion:
        """Read the structured document for one catalog row."""
        path = self.root / version.relative_path
        return RegulatoryVersion.model_validate_json(path.read_text(encoding="utf-8"))

    def load_current(self, celex: str, language: str = "en") -> RegulatoryVersion:
        """Read the catalog row that is current for one work and language."""
        catalog = self._read_catalog()
        matches = [
            version
            for version in catalog.versions
            if version.celex == celex and version.language == language and not version.superseded
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one current {language} record for {celex}; found {len(matches)}"
            )
        return self.load(matches[0])

    def _find(self, catalog: Catalog, document: RegulatoryVersion) -> StoredVersion | None:
        for version in catalog.versions:
            if (
                version.celex == document.celex
                and version.language == document.language
                and version.document_kind == document.document_kind
                and version.content_sha256 == document.content_sha256
            ):
                return version
        return None

    def _read_catalog(self) -> Catalog:
        if not self.catalog_path.is_file():
            return Catalog()
        return Catalog.model_validate_json(self.catalog_path.read_text(encoding="utf-8"))

    def _write_catalog(self, catalog: Catalog) -> None:
        _write_text(self.catalog_path, catalog.model_dump_json(indent=2))


def _same_work(version: StoredVersion, document: RegulatoryVersion) -> bool:
    return (
        version.celex == document.celex
        and version.language == document.language
        and version.document_kind == document.document_kind
    )


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
