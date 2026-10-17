import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.frozen_guard as _fg  # noqa: E402

# Frozen experiment records under results/ must never be written by tests.
# (1) session-level SHA-256 guard  (2) autouse redirect of test evidence writers
_FROZEN_RESULT_MARKERS = (
    "results/pilot1_preflight",
    "results/pilot1_live_admission_verified",
    "results/pilot1_final_admission_verified",
    "results/pilot1_final_offline",
    "results/pilot1_postmortem",
    "results/pilot1_live_run",
    "results/pilot1_hotfix_offline",
)


def _is_frozen_results_path(p: Path) -> bool:
    s = str(p).replace("\\", "/")
    return any(m in s for m in _FROZEN_RESULT_MARKERS) and "pytest_evidence" not in s


@pytest.fixture(scope="session", autouse=True)
def frozen_results_guard():
    """Assert every tracked results/ file is byte-identical after the session.

    Runs even when tests fail. If the process is hard-killed the source-level
    redirect (below) is the real protection — this guard is the detector.
    """
    before = _fg.snapshot()
    yield
    after = _fg.snapshot()
    _fg.assert_frozen_unchanged(before, after)


@pytest.fixture(autouse=True)
def _redirect_test_evidence_writes(tmp_path, monkeypatch):
    """Redirect ONLY modules that actually write evidence into frozen dirs.

    Modules that merely READ frozen artifacts (e.g. test_pilot1_postmortem)
    keep their real paths. Write helpers are identified by name.
    """
    write_helpers = {"_write", "write_evidence", "_write_evidence", "emit_evidence"}
    for mod in list(sys.modules.values()):
        if not any(hasattr(mod, h) for h in write_helpers):
            continue
        for attr in ("RESULTS", "OUT", "OUTPUT_DIR"):
            target = getattr(mod, attr, None)
            if isinstance(target, Path) and _is_frozen_results_path(target):
                redirected = tmp_path / "pytest_evidence" / target.name
                redirected.mkdir(parents=True, exist_ok=True)
                monkeypatch.setattr(mod, attr, redirected, raising=False)
