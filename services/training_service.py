"""
Training Service for Extraction Learning System

This service handles:
1. Saving user corrections from review
2. Analyzing corrections to learn extraction patterns
3. Generating and updating extraction rules
4. Providing learned rules to extractors
"""

import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from sqlmodel import Session, select
from models.training import (
    ExtractionRule, FieldCorrection, TrainingExample,
    ExtractionPattern, FieldCorrectionCreate
)

logger = logging.getLogger(__name__)


class TrainingService:
    """Service for managing extraction training and learning."""

    def __init__(self, session: Session):
        self.session = session

    # =========================================================================
    # CORRECTION HANDLING
    # =========================================================================

    def save_corrections(
        self,
        run_id: int,
        corrections: List[FieldCorrectionCreate],
        mark_validated: bool = True
    ) -> Tuple[int, int]:
        """
        Save field corrections from user review.

        Returns: (saved_count, error_count)
        """
        # Get run info from main database
        run_info = self._get_run_info(run_id)
        if not run_info:
            raise ValueError(f"Extraction run {run_id} not found")

        auction_type_id = run_info.get('auction_type_id', 1)
        document_id = run_info.get('document_id', run_id)
        extracted_text = run_info.get('extracted_text', '')

        saved_count = 0
        error_count = 0

        for correction in corrections:
            try:
                # Create field correction record
                fc = FieldCorrection(
                    extraction_run_id=run_id,
                    auction_type_id=auction_type_id,
                    document_id=document_id,
                    field_key=correction.field_key,
                    predicted_value=correction.predicted_value,
                    corrected_value=correction.corrected_value,
                    was_correct=correction.was_correct,
                    context_text=self._find_context(extracted_text, correction.corrected_value),
                    preceding_label=self._find_preceding_label(extracted_text, correction.corrected_value),
                )
                self.session.add(fc)
                saved_count += 1
            except Exception as e:
                logger.error(f"Error saving correction for {correction.field_key}: {e}")
                error_count += 1

        # Create training example
        if saved_count > 0:
            corrected_fields = {
                c.field_key: c.corrected_value or c.predicted_value
                for c in corrections
            }
            example = TrainingExample(
                auction_type_id=auction_type_id,
                document_id=document_id,
                corrected_fields=json.dumps(corrected_fields),
                raw_text=extracted_text[:5000] if extracted_text else None,
                is_validated=mark_validated,
                validated_at=datetime.utcnow() if mark_validated else None,
            )
            self.session.add(example)

        self.session.commit()

        # Trigger learning from corrections
        if saved_count > 0:
            try:
                self._learn_from_corrections(auction_type_id)
            except Exception as e:
                logger.error(f"Error during learning: {e}")

        return saved_count, error_count

    def _get_run_info(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get extraction run info from main database."""
        try:
            from api.database import get_connection
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM extraction_runs WHERE id = ?",
                    (run_id,)
                ).fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.warning(f"Could not get run info: {e}")
        return {'auction_type_id': 1, 'document_id': run_id, 'extracted_text': ''}

    def _find_context(self, text: str, value: str, window: int = 200) -> Optional[str]:
        """Find context around a value in text."""
        if not text or not value:
            return None

        pos = text.find(value)
        if pos == -1:
            return None

        start = max(0, pos - window)
        end = min(len(text), pos + len(value) + window)
        return text[start:end]

    def _find_preceding_label(self, text: str, value: str) -> Optional[str]:
        """Find the label that precedes a value in text."""
        if not text or not value:
            return None

        pos = text.find(value)
        if pos == -1:
            return None

        # Look at the line above the value
        before = text[:pos]
        lines = before.split('\n')
        if len(lines) >= 2:
            prev_line = lines[-2].strip()
            # Check if it looks like a label (ends with colon or is ALL CAPS)
            if prev_line.endswith(':') or (prev_line.isupper() and len(prev_line) > 3):
                return prev_line.rstrip(':')

        return None

    # =========================================================================
    # LEARNING
    # =========================================================================

    def _learn_from_corrections(self, auction_type_id: int):
        """Analyze corrections and update extraction rules."""
        # Get recent corrections for this auction type
        corrections = self.session.exec(
            select(FieldCorrection)
            .where(FieldCorrection.auction_type_id == auction_type_id)
            .where(FieldCorrection.is_processed == False)
            .order_by(FieldCorrection.created_at.desc())
            .limit(100)
        ).all()

        if not corrections:
            return

        # Group by field_key
        by_field: Dict[str, List[FieldCorrection]] = {}
        for c in corrections:
            if c.field_key not in by_field:
                by_field[c.field_key] = []
            by_field[c.field_key].append(c)

        # Learn patterns for each field
        for field_key, field_corrections in by_field.items():
            self._learn_field_patterns(auction_type_id, field_key, field_corrections)

        # Mark corrections as processed
        for c in corrections:
            c.is_processed = True
        self.session.commit()

    def _learn_field_patterns(
        self,
        auction_type_id: int,
        field_key: str,
        corrections: List[FieldCorrection]
    ):
        """Learn extraction patterns for a specific field."""
        # Collect labels from corrections
        labels = []
        for c in corrections:
            if c.preceding_label:
                labels.append(c.preceding_label)

        if not labels:
            return

        # Find common patterns
        label_patterns = list(set(labels))

        # Get or create rule
        rule = self.session.exec(
            select(ExtractionRule)
            .where(ExtractionRule.auction_type_id == auction_type_id)
            .where(ExtractionRule.field_key == field_key)
            .where(ExtractionRule.is_active == True)
        ).first()

        if not rule:
            rule = ExtractionRule(
                auction_type_id=auction_type_id,
                field_key=field_key,
                rule_type="label_below",
            )
            self.session.add(rule)

        # Update rule with learned patterns
        existing_patterns = rule.get_label_patterns()
        new_patterns = list(set(existing_patterns + label_patterns))
        rule.set_label_patterns(new_patterns)

        # Update confidence based on correction agreement
        correct_count = sum(1 for c in corrections if c.was_correct)
        rule.confidence = correct_count / len(corrections) if corrections else 0.5
        rule.validation_count += len(corrections)
        rule.updated_at = datetime.utcnow()

        self.session.commit()

    # =========================================================================
    # STATS AND QUERIES
    # =========================================================================

    def get_training_stats(self, auction_type_id: Optional[int] = None) -> Dict[str, Any]:
        """Get training statistics."""
        stats = {"by_auction_type": {}}

        # Get auction types from main database
        auction_types = self._get_auction_types()

        for at in auction_types:
            at_id = at['id']
            at_code = at['code']

            if auction_type_id and at_id != auction_type_id:
                continue

            # Count corrections
            correction_count = self.session.exec(
                select(FieldCorrection)
                .where(FieldCorrection.auction_type_id == at_id)
            ).all()

            # Count examples
            examples = self.session.exec(
                select(TrainingExample)
                .where(TrainingExample.auction_type_id == at_id)
            ).all()

            # Count rules
            rules = self.session.exec(
                select(ExtractionRule)
                .where(ExtractionRule.auction_type_id == at_id)
                .where(ExtractionRule.is_active == True)
            ).all()

            validated = sum(1 for e in examples if e.is_validated)
            avg_confidence = sum(r.confidence for r in rules) / len(rules) if rules else 0

            stats["by_auction_type"][at_code] = {
                "auction_type_id": at_id,
                "correction_count": len(correction_count),
                "total_examples": len(examples),
                "validated_examples": validated,
                "rules_count": len(rules),
                "avg_confidence": round(avg_confidence, 2),
            }

        return stats

    def _get_auction_types(self) -> List[Dict[str, Any]]:
        """Get auction types from main database."""
        try:
            from api.database import get_connection
            with get_connection() as conn:
                rows = conn.execute("SELECT id, code, name FROM auction_types").fetchall()
                return [dict(row) for row in rows]
        except Exception:
            # Return defaults if table doesn't exist
            return [
                {"id": 1, "code": "copart", "name": "Copart"},
                {"id": 2, "code": "iaa", "name": "IAA"},
                {"id": 3, "code": "manheim", "name": "Manheim"},
            ]

    def get_extraction_rules(
        self,
        auction_type_id: int,
        field_key: Optional[str] = None
    ) -> List[ExtractionRule]:
        """Get extraction rules for an auction type."""
        query = select(ExtractionRule).where(
            ExtractionRule.auction_type_id == auction_type_id,
            ExtractionRule.is_active == True
        )

        if field_key:
            query = query.where(ExtractionRule.field_key == field_key)

        return list(self.session.exec(query).all())

    def get_rules_for_extractor(self, auction_type_code: str) -> Dict[str, Any]:
        """Get rules in format suitable for extractors."""
        # Find auction type ID
        auction_types = self._get_auction_types()
        auction_type_id = None
        for at in auction_types:
            if at['code'].lower() == auction_type_code.lower():
                auction_type_id = at['id']
                break

        if not auction_type_id:
            return {}

        rules = self.get_extraction_rules(auction_type_id)

        result = {}
        for rule in rules:
            result[rule.field_key] = {
                "rule_type": rule.rule_type,
                "label_patterns": rule.get_label_patterns(),
                "exclude_patterns": rule.get_exclude_patterns(),
                "confidence": rule.confidence,
            }

        return result
