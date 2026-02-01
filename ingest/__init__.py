"""Email ingestion module."""

from ingest.email_reader import (
    Attachment as Attachment,
)
from ingest.email_reader import (
    EmailMessage as EmailMessage,
)
from ingest.email_reader import (
    EmailReader as EmailReader,
)
from ingest.email_reader import (
    create_email_reader as create_email_reader,
)

__all__ = ["Attachment", "EmailMessage", "EmailReader", "create_email_reader"]
