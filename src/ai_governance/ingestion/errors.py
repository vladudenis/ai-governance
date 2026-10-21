"""Failures from regulatory retrieval and parsing."""


class IngestionError(Exception):
    """Base error for the ingestion pipeline."""


class RetrievalError(IngestionError):
    """CELLAR could not be reached, or it returned an unexpected response."""


class DocumentNotFound(IngestionError):
    """The requested work, language, or Formex manifestation is absent."""


class MalformedDocument(IngestionError):
    """A notice or Formex payload is not usable structured XML."""


class IdentifierMismatch(IngestionError):
    """The retrieved document is not the CELEX or language that was requested."""
