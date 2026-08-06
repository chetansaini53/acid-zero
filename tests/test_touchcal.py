"""Unit tests for launcher/acid_touchcal.py (the resistive-touch calibration math).

Runnable two ways:
    python tests/test_touchcal.py        # standalone, no pytest needed
    pytest tests/test_touchcal.py        # if pytest is installed

The `test_parity_*` cases replicate the ORIGINAL inline algorithm that lived in
acidzero.py and assert the extracted module produces byte-identical results, so
the refactor is provably behaviour-preserving without a device.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "launcher"))
import acid_touchcal as tc  # noqa: E402

# The launcher's real 4 calibration targets (screen corners) + framebuffer size.
CAL_TARGETS = [(44, 46), (436, 46), (436, 274), (44, 274)]
W, H = 480, 320


# ---- reference copy of the ORIGINAL inline code (for the parity tests) --------
def _old_solve(cal_raws, targets):
    A = np.array([[float(r[0]), float(r[1]), 1.0] for r in cal_raws])
    txs = np.array([float(t[0]) for t in targets])
    tys = np.array([float(t[1]) for t in targets])
    cx_ = np.linalg.lstsq(A, txs, rcond=None)[0]
    cy_ = np.linalg.lstsq(A, tys, rcond=None)[0]
    px = A.dot(cx_); py = A.dot(cy_)
    res = float(np.max(((px - txs) ** 2 + (py - tys) ** 2) ** 0.5))
    coeffs = [float(cx_[0]), float(cx_[1]), float(cx_[2]),
              float(cy_[0]), float(cy_[1]), float(cy_[2])]
    return coeffs, res


def _old_map(CAL, rx, ry):
    sx = CAL[0] * rx + CAL[1] * ry + CAL[2]
    sy = CAL[3] * rx + CAL[4] * ry + CAL[5]
    return max(0, min(W - 1, int(round(sx)))), max(0, min(H - 1, int(round(sy))))


# ---- functional tests ---------------------------------------------------------
def test_recovers_known_affine():
    """Points generated from a known affine are fit back with ~0 residual."""
    true = [0.17, 0.002, -30.0, -0.001, -0.13, 300.0]     # a plausible raw->screen map
    raws = [(300, 3600), (3500, 3500), (3600, 400), (350, 350)]
    # exact float targets from the true map (no int rounding) so the fit is exact
    targets = [(true[0] * rx + true[1] * ry + true[2],
                true[3] * rx + true[4] * ry + true[5]) for rx, ry in raws]
    coeffs, residual = tc.solve_calibration(raws, targets)
    assert residual < 1e-6, "consistent affine data must fit exactly, got %.6g" % residual
    # recovered coeffs reproduce the same clamped pixel mapping as the true map
    for rx, ry in raws:
        assert tc.apply_calibration(coeffs, rx, ry, W, H) == tc.apply_calibration(true, rx, ry, W, H)


def test_residual_flags_bad_calibration():
    """An inconsistent tap (outlier) yields a large residual the launcher rejects."""
    raws = [(300, 3600), (3500, 3500), (3600, 400), (2000, 2000)]  # last is off-pattern
    _, residual = tc.solve_calibration(raws, CAL_TARGETS)
    assert residual > 45, "a bad point set must exceed the 45px reject threshold"


def test_apply_clamps_offscreen():
    """A mapping that lands off-screen is clamped to the display bounds."""
    coeffs = [10.0, 0.0, 100000.0, 0.0, 10.0, -100000.0]   # blows way past both edges
    x, y = tc.apply_calibration(coeffs, 5, 5, W, H)
    assert (x, y) == (W - 1, 0)


def test_coeffs_shape():
    coeffs, _ = tc.solve_calibration([(1, 2), (3, 4), (5, 6), (7, 8)], CAL_TARGETS)
    assert len(coeffs) == tc.NUM_COEFFS
    assert all(isinstance(c, float) for c in coeffs)


# ---- parity tests: extracted module == original inline code -------------------
def test_parity_solve_random():
    rng = np.random.RandomState(1234)
    for _ in range(300):
        raws = [(int(rng.randint(150, 3900)), int(rng.randint(150, 3900))) for _ in range(4)]
        new_c, new_r = tc.solve_calibration(raws, CAL_TARGETS)
        old_c, old_r = _old_solve(raws, CAL_TARGETS)
        assert new_c == old_c, "coeffs diverged: %r vs %r" % (new_c, old_c)
        assert new_r == old_r, "residual diverged: %r vs %r" % (new_r, old_r)


def test_parity_apply_random():
    rng = np.random.RandomState(4321)
    cal = [480.0 / 2816.0, 0.0, -663 * 480.0 / 2816.0,
           0.0, -320.0 / 2512.0, 2948 * 320.0 / 2512.0]     # the launcher's default CAL
    for _ in range(2000):
        rx, ry = int(rng.randint(0, 4096)), int(rng.randint(0, 4096))
        assert tc.apply_calibration(cal, rx, ry, W, H) == _old_map(cal, rx, ry)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print("\nAll %d tests passed." % len(fns))
