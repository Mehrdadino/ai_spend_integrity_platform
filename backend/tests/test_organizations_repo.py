"""Unit tests for organization repository create + slug rules (no Postgres)."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock

from app.models.organization import Organization
from app.repositories.organizations import (
    OrganizationSlugConflictError,
    create_organization,
)


class TestCreateOrganization(unittest.TestCase):
    def test_rejects_invalid_slug_characters(self) -> None:
        session = MagicMock()
        with self.assertRaises(ValueError):
            create_organization(session, name="x", slug="bad__slug")

    def test_rejects_duplicate_slug(self) -> None:
        session = MagicMock()
        existing = Organization(
            id=uuid.uuid4(),
            name="Old",
            slug="acme",
        )

        def scalar_side_effect(*_args, **_kwargs):
            # First call: duplicate check inside ``create_organization`` finds row.
            return existing

        session.scalar.side_effect = scalar_side_effect
        with self.assertRaises(OrganizationSlugConflictError):
            create_organization(session, name="New", slug="acme")
