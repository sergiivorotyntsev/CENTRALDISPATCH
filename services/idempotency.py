"""Idempotency storage for email deduplication."""
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class IdempotencyStore:
    def __init__(self, db_path: str = "processed_emails.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    thread_root_id TEXT,
                    message_id TEXT,
                    attachment_hash TEXT,
                    source_type TEXT,
                    result_type TEXT,
                    result_id TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def compute_attachment_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def extract_thread_root_id(message_id: Optional[str], in_reply_to: Optional[str], references: Optional[str]) -> str:
        if references:
            refs = references.strip().split()
            if refs:
                return refs[0].strip('<>')
        if in_reply_to:
            return in_reply_to.strip('<>')
        if message_id:
            return message_id.strip('<>')
        return f"unknown-{datetime.utcnow().isoformat()}"

    def generate_idempotency_key(self, thread_root_id: str, attachment_hash: str) -> str:
        return f"{thread_root_id}:{attachment_hash}"

    def is_processed(self, idempotency_key: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT 1 FROM processed_items WHERE idempotency_key = ?", (idempotency_key,))
            return cursor.fetchone() is not None

    def is_attachment_processed_in_thread(self, thread_root_id: str, attachment_hash: str) -> Tuple[bool, Optional[str]]:
        key = self.generate_idempotency_key(thread_root_id, attachment_hash)
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT result_id FROM processed_items WHERE idempotency_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return True, row['result_id']
            return False, None

    def mark_processed(self, thread_root_id: str, message_id: str, attachment_hash: str, source_type: str, result_type: str, result_id: str, metadata: Optional[str] = None) -> bool:
        key = self.generate_idempotency_key(thread_root_id, attachment_hash)
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """INSERT INTO processed_items (idempotency_key, thread_root_id, message_id, attachment_hash, source_type, result_type, result_id, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (key, thread_root_id, message_id, attachment_hash, source_type, result_type, result_id, metadata)
                )
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
