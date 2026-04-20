"""Phase 3 DISP-04 — Flame-approved CustomEDID profile emission.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-03
inside :func:`server.session_manager._generate_edid` — selects a
Flame-approved monitor-profile name (Eizo CG279X-class or in-house
TGC-Flame-001 generator output) so Flame's monitor-config dialog accepts
the Xvfb session without complaint.

The generator stays as a fallback path for users without the shipped
EDID binary. Not user-configurable in v1.
"""
import pytest


def test_flame_profile():
    """DISP-04 — generated EDID reports a Flame-approved monitor name.

    Planner picks the exact profile (Eizo CG279X-like industry-standard
    grading monitor, or TGC-Flame-001 locally-generated profile). Test
    asserts the emitted ``ProductName`` string matches one of the
    approved values.
    """
    pytest.importorskip("server.session_manager")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (DISP-04)")
