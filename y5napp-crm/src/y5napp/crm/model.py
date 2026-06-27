from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import AsyncGenerator


@dataclass
class Contact:
    id: str = ""
    name: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""
    street: str = ""
    zip: str = ""
    city: str = ""
    country: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
