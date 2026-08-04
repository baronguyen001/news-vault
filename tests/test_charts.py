from __future__ import annotations

import pytest

from newsvault.charts import bar_chart, donut_chart, heat_grid, sparkline, stacked_bars

NORMAL_CASES = [
    (bar_chart, ([("A", 10), ("B", 20)],), {"title": "Bar"}),
    (donut_chart, ([("A", 10), ("B", 20)],), {"title": "Donut"}),
    (sparkline, ([1, 3, 2],), {}),
    (
        stacked_bars,
        (["2026-08-01", "2026-08-02"], {"S1": [1, 2], "S2": [3, 4]}),
        {"title": "Stack"},
    ),
    (
        heat_grid,
        (["R1"], ["C1"], {("R1", "C1"): 5}),
        {"title": "Heat"},
    ),
]

EMPTY_CASES = [
    (bar_chart, ([],), {"title": "Empty"}),
    (donut_chart, ([],), {"title": "Empty"}),
    (sparkline, ([],), {}),
    (stacked_bars, ([], {}), {"title": "Empty"}),
    (heat_grid, ([], [], {}), {"title": "Empty"}),
]


@pytest.mark.parametrize(("func", "args", "kwargs"), NORMAL_CASES)
def test_chart_renders_normal_input(func, args, kwargs):
    svg = func(*args, **kwargs)
    assert isinstance(svg, str)
    assert svg.startswith("<svg")
    assert "#000" not in svg
    assert "#fff" not in svg
    assert "black" not in svg
    assert "white" not in svg


@pytest.mark.parametrize(("func", "args", "kwargs"), EMPTY_CASES)
def test_chart_handles_empty_input(func, args, kwargs):
    svg = func(*args, **kwargs)
    assert isinstance(svg, str)
    assert svg.startswith("<svg")
    assert "#000" not in svg
    assert "#fff" not in svg
    assert "black" not in svg
    assert "white" not in svg


def test_bar_chart_collapses_overflow_into_khac():
    data = [(f"Item {i}", float(i)) for i in range(1, 15)]
    svg = bar_chart(data, title="Overflow", max_bars=10)
    assert "Khác" in svg


def test_donut_chart_collapses_overflow_into_khac():
    data = [(f"Slice {i}", float(i)) for i in range(1, 10)]
    svg = donut_chart(data, title="Overflow", max_slices=6)
    assert "Khác" in svg
