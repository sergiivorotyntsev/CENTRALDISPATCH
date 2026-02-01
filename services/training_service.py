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
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlmodel import Session, select
from models.training import (
    ExtractionRule, FieldCorrection, TrainingExample,
    ExtractionPattern, FieldCorrectionCreate, TrainingSubmission
)
from models.document import Document
from models.extraction import ExtractionRun
from models.auction import AuctionType


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
        # Get the extraction run
        run = self.session.get(ExtractionRun, run_id)
        if not run:
            raise ValueError(f"Extraction run {run_id} not found")

        saved_count = 0
        error_count = 0

        # Get document for context
        document = self.session.get(Document, run.document_id)
        raw_text = document.raw_text if document else None

        for correction in corrections:
            try:
                # Find context in document text
                context_text = None
                preceding_label = None

                if raw_text and correction.corrected_value:
                    context_text, preceding_label = self._find_value_context(
                        raw_text, correction.corrected_value
                    )

                # Create correction record
                field_correction = FieldCorrection(
                    extraction_run_id=run_id,
                    auction_type_id=run.auction_type_id,
                    document_id=run.document_id,
                    field_key=correction.field_key,
                    predicted_value=correction.predicted_value,
                    corrected_value=correction.corrected_value,
                    was_correct=correction.was_correct,
                    context_text=context_text,
                    preceding_label=preceding_label,
                    is_processed=False,
                )
                self.session.add(field_correction)
                saved_count += 1

            except Exception as e:
                print(f"Error saving correction for {correction.field_key}: {e}")
                error_count += 1

        # Create or update training example
        if mark_validated and saved_count > 0:
            self._create_training_example(run, corrections)

        self.session.commit()

        # Trigger rule learning in background
        self._learn_from_corrections(run.auction_type_id)

        return saved_count, error_count

    def _find_value_context(
        self,
        text: str,
        value: str,
        context_chars: int = 200
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Find the context around a value in the document text.

        Returns: (context_text, preceding_label)
        """
        if not value or not text:
            return None, None

        # Find the value in text
        value_clean = value.strip()
        pos = text.find(value_clean)

        if pos == -1:
            # Try case-insensitive search
            pos = text.lower().find(value_clean.lower())

        if pos == -1:
            return None, None

        # Extract context
        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(value_clean) + context_chars)
        context = text[start:end]

        # Try to find preceding label
        before_value = text[max(0, pos - 100):pos]
        label_match = re.search(
            r'([A-Z][A-Z\s]+(?:OF\s+)?[A-Z]*)[:\s]*$',
            before_value,
            re.IGNORECASE
        )
        preceding_label = label_match.group(1).strip() if label_match else None

        return context, preceding_label

    def _create_training_example(
        self,
        run: ExtractionRun,
        corrections: List[FieldCorrectionCreate]
    ):
        """Create a training example from corrections."""
        # Build corrected fields dict
        corrected_fields = {}
        for c in corrections:
            if c.corrected_value is not None:
                corrected_fields[c.field_key] = c.corrected_value
            elif c.was_correct and c.predicted_value is not None:
                corrected_fields[c.field_key] = c.predicted_value

        # Get document text
        document = self.session.get(Document, run.document_id)
        raw_text = document.raw_text if document else None

        # Calculate quality score
        quality_score = len([c for c in corrections if c.corrected_value or c.was_correct]) / max(len(corrections), 1)

        # Check if example already exists
        existing = self.session.exec(
            select(TrainingExample).where(
                TrainingExample.document_id == run.document_id,
                TrainingExample.auction_type_id == run.auction_type_id
            )
        ).first()

        if existing:
            # Update existing example
            existing.set_corrected_fields(corrected_fields)
            existing.quality_score = quality_score
            existing.is_validated = True
            existing.validated_at = datetime.utcnow()
        else:
            # Create new example
            example = TrainingExample(
                auction_type_id=run.auction_type_id,
                document_id=run.document_id,
                corrected_fields=json.dumps(corrected_fields),
                raw_text=raw_text[:10000] if raw_text else None,  # Limit size
                quality_score=quality_score,
                is_validated=True,
                validated_at=datetime.utcnow(),
                dataset_split="train",
            )
            self.session.add(example)

    # =========================================================================
    # LEARNING & RULE GENERATION
    # =========================================================================

    def _learn_from_corrections(self, auction_type_id: int):
        """
        Analyze recent corrections and update extraction rules.

        This is the core learning algorithm that:
        1. Groups corrections by field
        2. Identifies patterns in correct extractions
        3. Updates or creates extraction rules
        """
        # Get unprocessed corrections for this auction type
        corrections = self.session.exec(
            select(FieldCorrection).where(
                FieldCorrection.auction_type_id == auction_type_id,
                FieldCorrection.is_processed == False,
                FieldCorrection.corrected_value != None
            )
        ).all()

        if not corrections:
            return

        # Group by field
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
        """Learn extraction patterns for a specific field from corrections."""

        # Collect preceding labels
        labels = [c.preceding_label for c in corrections if c.preceding_label]
        label_counts: Dict[str, int] = {}
        for label in labels:
            label_clean = label.upper().strip()
            label_counts[label_clean] = label_counts.get(label_clean, 0) + 1

        # Find most common labels
        if label_counts:
            sorted_labels = sorted(label_counts.items(), key=lambda x: -x[1])
            top_labels = [label for label, count in sorted_labels if count >= 1][:5]

            if top_labels:
                # Create or update extraction rule
                self._update_extraction_rule(
                    auction_type_id,
                    field_key,
                    label_patterns=top_labels,
                    rule_type="label_below",
                    validation_count=len(corrections)
                )

        # Learn negative patterns (what was incorrectly extracted)
        wrong_patterns = []
        for c in corrections:
            if not c.was_correct and c.predicted_value:
                # The predicted value was wrong - find what label preceded it
                if c.context_text and c.predicted_value in c.context_text:
                    # This helps identify which sections to AVOID
                    wrong_patterns.append(c.predicted_value[:50])

        if wrong_patterns:
            self._update_extraction_rule(
                auction_type_id,
                field_key,
                exclude_patterns=wrong_patterns[:3],  # Top 3 patterns to avoid
                is_update=True
            )

    def _update_extraction_rule(
        self,
        auction_type_id: int,
        field_key: str,
        label_patterns: List[str] = None,
        exclude_patterns: List[str] = None,
        rule_type: str = "label_below",
        validation_count: int = 1,
        is_update: bool = False
    ):
        """Create or update an extraction rule."""

        # Find existing rule
        existing = self.session.exec(
            select(ExtractionRule).where(
                ExtractionRule.auction_type_id == auction_type_id,
                ExtractionRule.field_key == field_key,
                ExtractionRule.rule_type == rule_type
            )
        ).first()

        if existing:
            # Update existing rule
            if label_patterns:
                current_patterns = existing.get_label_patterns()
                # Merge patterns, keeping most frequent
                all_patterns = list(set(current_patterns + label_patterns))
                existing.set_label_patterns(all_patterns[:10])  # Keep top 10

            if exclude_patterns:
                current_exclude = existing.get_exclude_patterns()
                all_exclude = list(set(current_exclude + exclude_patterns))
                existing.set_exclude_patterns(all_exclude[:10])

            existing.validation_count += validation_count
            existing.confidence = min(0.95, 0.5 + (existing.validation_count * 0.05))
            existing.updated_at = datetime.utcnow()

        else:
            # Create new rule
            rule = ExtractionRule(
                auction_type_id=auction_type_id,
                field_key=field_key,
                rule_type=rule_type,
                label_patterns=json.dumps(label_patterns or []),
                exclude_patterns=json.dumps(exclude_patterns or []),
                position_hints="[]",
                priority=0,
                confidence=0.5,
                validation_count=validation_count,
                is_active=True,
            )
            self.session.add(rule)

    # =========================================================================
    # RULE RETRIEVAL FOR EXTRACTORS
    # =========================================================================

    def get_extraction_rules(
        self,
        auction_type_id: int,
        field_key: str = None
    ) -> List[ExtractionRule]:
        """
        Get extraction rules for an auction type.

        Used by extractors to apply learned rules during extraction.
        """
        query = select(ExtractionRule).where(
            ExtractionRule.auction_type_id == auction_type_id,
            ExtractionRule.is_active == True
        )

        if field_key:
            query = query.where(ExtractionRule.field_key == field_key)

        query = query.order_by(ExtractionRule.confidence.desc())

        return list(self.session.exec(query).all())

    def get_rules_for_extractor(self, auction_type_code: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all rules for an auction type in a format suitable for extractors.

        Returns a dict keyed by field_key with rule details.
        """
        # Find auction type
        auction_type = self.session.exec(
            select(AuctionType).where(AuctionType.code == auction_type_code)
        ).first()

        if not auction_type:
            return {}

        rules = self.get_extraction_rules(auction_type.id)

        result = {}
        for rule in rules:
            if rule.field_key not in result:
                result[rule.field_key] = {
                    "label_patterns": [],
                    "exclude_patterns": [],
                    "rule_type": rule.rule_type,
                    "confidence": rule.confidence,
                }

            # Merge patterns
            result[rule.field_key]["label_patterns"].extend(rule.get_label_patterns())
            result[rule.field_key]["exclude_patterns"].extend(rule.get_exclude_patterns())

            # Keep highest confidence
            if rule.confidence > result[rule.field_key]["confidence"]:
                result[rule.field_key]["confidence"] = rule.confidence

        return result

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_training_stats(self, auction_type_id: int = None) -> Dict[str, Any]:
        """Get training statistics for auction types."""

        if auction_type_id:
            auction_types = [self.session.get(AuctionType, auction_type_id)]
        else:
            auction_types = list(self.session.exec(select(AuctionType)).all())

        stats = {"by_auction_type": {}}

        for at in auction_types:
            if not at:
                continue

            # Count training examples
            examples = self.session.exec(
                select(TrainingExample).where(
                    TrainingExample.auction_type_id == at.id
                )
            ).all()

            validated = [e for e in examples if e.is_validated]

            # Count corrections
            corrections_count = len(list(self.session.exec(
                select(FieldCorrection).where(
                    FieldCorrection.auction_type_id == at.id
                )
            ).all()))

            # Count rules
            rules = list(self.session.exec(
                select(ExtractionRule).where(
                    ExtractionRule.auction_type_id == at.id,
                    ExtractionRule.is_active == True
                )
            ).all())

            avg_confidence = sum(r.confidence for r in rules) / max(len(rules), 1)

            stats["by_auction_type"][at.code] = {
                "total": len(examples),
                "validated": len(validated),
                "corrections": corrections_count,
                "rules": len(rules),
                "avg_confidence": round(avg_confidence, 2),
            }

        return stats
