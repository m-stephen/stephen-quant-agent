from __future__ import annotations

import math
from collections.abc import Sequence


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("OLS controls are singular within a decision cross-section")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            multiplier = augmented[row][column]
            augmented[row] = [
                value - multiplier * pivot_value
                for value, pivot_value in zip(
                    augmented[row], augmented[column], strict=True
                )
            ]
    return [augmented[index][-1] for index in range(size)]


def ols_residuals(
    target: Sequence[float], controls: Sequence[Sequence[float]]
) -> list[float]:
    """Fit an intercept plus controls and return deterministic OLS residuals."""

    values = [float(value) for value in target]
    design_controls = [[float(value) for value in row] for row in controls]
    if not values or len(values) != len(design_controls):
        raise ValueError("OLS target and controls must have the same non-zero length")
    width = len(design_controls[0])
    if width < 1 or any(len(row) != width for row in design_controls):
        raise ValueError("OLS controls must have a consistent non-zero width")
    numeric = (*values, *(value for row in design_controls for value in row))
    if any(not math.isfinite(value) for value in numeric):
        raise ValueError("OLS inputs must be finite")
    design = [[1.0, *row] for row in design_controls]
    columns = width + 1
    gram = [
        [sum(row[left] * row[right] for row in design) for right in range(columns)]
        for left in range(columns)
    ]
    moment = [
        sum(row[index] * value for row, value in zip(design, values, strict=True))
        for index in range(columns)
    ]
    coefficients = _solve(gram, moment)
    return [
        value
        - sum(
            weight * coefficient
            for weight, coefficient in zip(row, coefficients, strict=True)
        )
        for row, value in zip(design, values, strict=True)
    ]
