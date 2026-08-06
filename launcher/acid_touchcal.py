"""Resistive-touch calibration for the Acid Zero launcher.

The 3.5" panel's touch controller reports raw ADC coordinates whose axes are
rotated, scaled and offset relative to the framebuffer's pixel grid (and the
mapping differs per panel and per boot orientation). We recover the mapping with
a **4-point affine calibration solved by least squares**:

    [ x ]   [ a  b  c ] [ rx ]
    [ y ] = [ d  e  f ] [ ry ]
                        [ 1  ]

The user taps four known screen targets (the screen corners); each tap gives a
raw (rx, ry) that should map to a known (tx, ty). Stacking the four points gives
an over-determined system A·k = t which `numpy.linalg.lstsq` solves for the six
coefficients. We then measure the **worst-corner residual** (max reprojection
error in pixels) and let the caller *reject* a bad calibration rather than ship a
silently misaligned screen — the fix for the original "stale raw coords poison
the matrix → mid-screen targets missed" bug.

Pure + hardware-independent so it is unit-tested off-device (see
`tests/test_touchcal.py`). The launcher owns only the acceptance threshold and
the persisted `CAL` vector; the math lives here.
"""
from __future__ import annotations

import numpy as np

# Six affine coefficients, stored/persisted as a flat list [a, b, c, d, e, f]:
#   x = a*rx + b*ry + c ,  y = d*rx + e*ry + f
NUM_COEFFS = 6


def solve_calibration(raw_points, targets):
    """Fit the affine touch->screen matrix from paired points.

    Args:
        raw_points: iterable of (rx, ry) raw touch coordinates, one per target.
        targets:    iterable of (tx, ty) known screen pixel coordinates.
                    Both must be the same length (>= 3 for a solvable fit).

    Returns:
        (coeffs, residual):
            coeffs   - list of 6 floats [a, b, c, d, e, f].
            residual - float, the maximum per-point reprojection error in pixels
                       (0 for a perfect fit). The caller compares this against an
                       acceptance threshold to accept or reject the calibration.
    """
    A = np.array([[float(r[0]), float(r[1]), 1.0] for r in raw_points])
    txs = np.array([float(t[0]) for t in targets])
    tys = np.array([float(t[1]) for t in targets])
    cx = np.linalg.lstsq(A, txs, rcond=None)[0]
    cy = np.linalg.lstsq(A, tys, rcond=None)[0]
    px = A.dot(cx)
    py = A.dot(cy)
    residual = float(np.max(((px - txs) ** 2 + (py - tys) ** 2) ** 0.5))
    coeffs = [float(cx[0]), float(cx[1]), float(cx[2]),
              float(cy[0]), float(cy[1]), float(cy[2])]
    return coeffs, residual


def apply_calibration(coeffs, rx, ry, width, height):
    """Map a raw touch (rx, ry) to a screen pixel, clamped to the display.

    Args:
        coeffs: 6 affine coefficients [a, b, c, d, e, f] from solve_calibration().
        rx, ry: raw touch coordinates from the controller.
        width, height: framebuffer size, so the result is clamped on-screen.

    Returns:
        (x, y) integer pixel coordinates, each clamped to [0, width-1]/[0, height-1].
    """
    sx = coeffs[0] * rx + coeffs[1] * ry + coeffs[2]
    sy = coeffs[3] * rx + coeffs[4] * ry + coeffs[5]
    return (max(0, min(width - 1, int(round(sx)))),
            max(0, min(height - 1, int(round(sy)))))
