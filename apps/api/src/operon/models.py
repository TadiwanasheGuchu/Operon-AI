"""Imports every ORM model so Base.metadata is complete (Alembic, tests).

Add each new module's models here; tests/test_database.py fails if a table is missing.
"""

from operon.core import models as core_models
from operon.modules.agents import models as agents_models
from operon.modules.ai import models as ai_models
from operon.modules.audit import models as audit_models
from operon.modules.dashboard import models as dashboard_models
from operon.modules.identity import models as identity_models
from operon.modules.incidents import models as incidents_models
from operon.modules.integrations import models as integrations_models
from operon.modules.intelligence import models as intelligence_models
from operon.modules.notifications import models as notifications_models
from operon.modules.operations import models as operations_models
from operon.modules.organisations import models as organisations_models
from operon.modules.permissions import models as permissions_models
from operon.modules.workflows import models as workflows_models

__all__ = [
    "agents_models",
    "ai_models",
    "audit_models",
    "core_models",
    "dashboard_models",
    "identity_models",
    "incidents_models",
    "integrations_models",
    "intelligence_models",
    "notifications_models",
    "operations_models",
    "organisations_models",
    "permissions_models",
    "workflows_models",
]
