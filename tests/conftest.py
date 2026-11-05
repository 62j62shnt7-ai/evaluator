"""Skip tests that depend on excluded, user-supplied source workbooks when absent."""
from __future__ import annotations
import pytest
from tests.source_config import SOURCE_ROOT

SOURCE_MODULES = {
    "tests/acceptance/test_sources.py",
    "tests/integration/test_adapters.py",
    "tests/integration/test_app_services.py",
    "tests/integration/test_batch_evaluation.py",
    "tests/integration/test_engineering_records.py",
    "tests/integration/test_quick_workflow.py",
    "tests/integration/test_whole_sheet.py",
    "tests/integration/test_workspace.py",
    "tests/integration/test_template_reproduction.py",
}


def pytest_collection_modifyitems(config, items):
    required = [SOURCE_ROOT / "workbooks", SOURCE_ROOT / "codes"]
    missing = [path for path in required if not path.is_dir()]
    if not missing:
        return
    reason = (
        "requires excluded workbook/code sources under "
        f"{SOURCE_ROOT}; set UT_EVALUATOR_SOURCES to the configured sources/ directory"
    )
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if any(item.nodeid.startswith(module) for module in SOURCE_MODULES):
            item.add_marker(marker)
