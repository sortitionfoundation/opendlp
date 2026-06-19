"""ABOUTME: Phase 2 pilot — runs the assembly CRUD e2e tests against the fake-backed app
ABOUTME: Reuses the exact test bodies from test_assembly_crud via the fake_pilot conftest fixtures"""

# Re-export the assembly CRUD test classes so pytest collects and runs them in
# this module, where the fake_pilot conftest supplies a FakeStore-backed app and
# in-memory data fixtures instead of the PostgreSQL ones.
from tests.e2e.test_assembly_crud import (  # noqa: F401
    TestAssemblyCreateView,
    TestAssemblyEditView,
    TestAssemblyListView,
    TestAssemblyPermissions,
    TestAssemblyViewDetail,
    TestAssemblyWorkflowIntegration,
)
