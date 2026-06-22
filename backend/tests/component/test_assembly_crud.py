"""ABOUTME: Component tests for assembly CRUD — runs the e2e assembly bodies against the fake-backed app
ABOUTME: Reuses the exact test bodies from tests/e2e/test_assembly_crud via the component conftest fixtures"""

# Re-export the assembly CRUD test classes so pytest collects and runs them in
# this module, where the component conftest supplies a FakeStore-backed app and
# in-memory data fixtures instead of the PostgreSQL ones. The PostgreSQL copy in
# tests/e2e/test_assembly_crud.py remains the real-DB coverage.
from tests.e2e.test_assembly_crud import (  # noqa: F401
    TestAssemblyCreateView,
    TestAssemblyEditView,
    TestAssemblyListView,
    TestAssemblyPermissions,
    TestAssemblyViewDetail,
    TestAssemblyWorkflowIntegration,
)
