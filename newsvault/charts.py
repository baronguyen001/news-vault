from __future__ import annotations

import html
import math
from collections.abc import Collection, Mapping, Sequence

_COLOR_FALLBACKS = [
    "#4f7cff",
    "#ff6b6b",
    "#51cf66",
    "#fcc419",
    "#a9e34b",
    "#da77f2",
]


def _color(index: int) -> str:
    fallback = _COLOR_FALLBACKS[index % len(_COLOR_FALLBACKS)]
    return f"var(--c{index % 6 + 1}, {fallback})"


def _fmt(value: float) -> str:
    text = f"{value:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _svg_open(width: int, height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img"><title>{html.escape(title)}</title>'
    )


def _ring_segment(
    center_x: float,
    center_y: float,
    outer: float,
    inner: float,
    start: float,
    end: float,
) -> str:
    sweep = end - start
    if sweep >= 2.0 * math.pi - 1e-9:
        return _full_ring(center_x, center_y, outer, inner)

    x1o = center_x + outer * math.cos(start)
    y1o = center_y + outer * math.sin(start)
    x2o = center_x + outer * math.cos(end)
    y2o = center_y + outer * math.sin(end)
    x1i = center_x + inner * math.cos(start)
    y1i = center_y + inner * math.sin(start)
    x2i = center_x + inner * math.cos(end)
    y2i = center_y + inner * math.sin(end)
    large = 1 if sweep > math.pi else 0

    return (
        f"M {_fmt(x1o)} {_fmt(y1o)} A {_fmt(outer)} {_fmt(outer)} 0 {large} 1 "
        f"{_fmt(x2o)} {_fmt(y2o)} L {_fmt(x2i)} {_fmt(y2i)} "
        f"A {_fmt(inner)} {_fmt(inner)} 0 {large} 0 {_fmt(x1i)} {_fmt(y1i)} Z"
    )


def _full_ring(center_x: float, center_y: float, outer: float, inner: float) -> str:
    o_top = (center_x, center_y - outer)
    o_bottom = (center_x, center_y + outer)
    i_top = (center_x, center_y - inner)
    i_bottom = (center_x, center_y + inner)
    return (
        f"M {_fmt(o_top[0])} {_fmt(o_top[1])} "
        f"A {_fmt(outer)} {_fmt(outer)} 0 1 1 {_fmt(o_bottom[0])} {_fmt(o_bottom[1])} "
        f"A {_fmt(outer)} {_fmt(outer)} 0 1 1 {_fmt(o_top[0])} {_fmt(o_top[1])} "
        f"L {_fmt(i_bottom[0])} {_fmt(i_bottom[1])} "
        f"A {_fmt(inner)} {_fmt(inner)} 0 1 0 {_fmt(i_top[0])} {_fmt(i_top[1])} "
        f"A {_fmt(inner)} {_fmt(inner)} 0 1 0 {_fmt(i_bottom[0])} {_fmt(i_bottom[1])} Z"
    )


def bar_chart(
    data: Sequence[tuple[str, float]],
    *,
    title: str,
    width: int = 720,
    bar_height: int = 26,
    max_bars: int = 10,
    emphasis: Collection[str] = (),
    emphasis_label: str = "",
    rest_label: str = "",
) -> str:
    """Render a horizontal bar chart as a deterministic inline SVG.

    Pass ``max_bars=len(data)`` to show every row instead of folding the tail into a
    "Khác" bucket. ``emphasis`` colours the named rows differently and, together with
    ``emphasis_label``/``rest_label``, draws a two-swatch legend explaining the split.
    """
    if not data or max_bars < 1:
        height = 60
        return (
            _svg_open(width, height, title)
            + f'<rect x="10" y="36" width="{width - 20}" height="14" fill="none" '
            + 'stroke="currentColor" stroke-opacity="0.3"/></svg>'
        )

    sorted_data = sorted(data, key=lambda item: (-item[1], item[0]))
    if len(sorted_data) > max_bars:
        top = sorted_data[: max_bars - 1]
        other_sum = sum(value for _, value in sorted_data[max_bars - 1 :])
        display = top + [("Khác", other_sum)]
    else:
        display = sorted_data

    emphasised = set(emphasis)
    legend = bool(emphasised and emphasis_label and rest_label)

    margin_left = 200
    margin_right = 80
    top_margin = 40 if not legend else 62
    plot_width = width - margin_left - margin_right
    max_value = max(max(0.0, value) for _, value in display)
    chart_height = top_margin + len(display) * bar_height + 16

    parts = [_svg_open(width, chart_height, title)]

    if legend:
        for offset, (swatch, label) in enumerate(
            ((_color(1), emphasis_label), (_color(0), rest_label))
        ):
            x = 8 + offset * 180
            parts.append(
                f'<rect x="{x}" y="18" width="10" height="10" rx="2" fill="{swatch}"/>'
                f'<text x="{x + 16}" y="27" font-size="12" fill="currentColor">'
                f"{html.escape(label)}</text>"
            )

    for index, (label, value) in enumerate(display):
        draw_value = max(0.0, value)
        bar_width = (draw_value / max_value * plot_width) if max_value > 0 else 0.0
        y = top_margin + index * bar_height
        text_y = y + bar_height / 2
        fill = _color(1) if label in emphasised else _color(0)

        parts.append(
            f'<rect x="{margin_left}" y="{y + 2}" width="{bar_width:.2f}" '
            f'height="{bar_height - 4}" rx="2" fill="{fill}"/>'
        )
        parts.append(
            f'<text x="8" y="{text_y:.2f}" text-anchor="start" '
            f'dominant-baseline="middle" font-size="12" fill="currentColor">'
            f"{html.escape(label)}</text>"
        )
        parts.append(
            f'<text x="{margin_left + bar_width + 6:.2f}" y="{text_y:.2f}" '
            f'text-anchor="start" dominant-baseline="middle" font-size="11" '
            f'fill="currentColor">{_fmt(value)}</text>'
        )

    return "".join(parts) + "</svg>"


def donut_chart(
    data: Sequence[tuple[str, float]],
    *,
    title: str,
    size: int = 220,
    max_slices: int = 6,
) -> str:
    """Render a donut chart with a legend as a deterministic inline SVG.

    The legend is not decoration: without labels a donut cannot be read, and the
    ``Khác`` bucket that absorbs everything past ``max_slices`` would be invisible.
    """
    legend_width = 300
    total_width = size + legend_width
    if not data or max_slices < 1:
        return _svg_open(total_width, size, title) + "</svg>"

    sorted_data = sorted(data, key=lambda item: (-item[1], item[0]))
    if len(sorted_data) > max_slices:
        top = sorted_data[: max_slices - 1]
        other_sum = sum(value for _, value in sorted_data[max_slices - 1 :])
        display = top + [("Khác", other_sum)]
    else:
        display = sorted_data

    total = sum(max(0.0, value) for _, value in display)
    if total <= 0.0:
        return _svg_open(total_width, size, title) + "</svg>"

    center = size / 2.0
    outer_radius = size * 0.45
    inner_radius = size * 0.25
    start_angle = -math.pi / 2.0

    parts = [_svg_open(total_width, size, title)]
    for index, (_label, value) in enumerate(display):
        angle = max(0.0, value) / total * 2.0 * math.pi
        path = _ring_segment(
            center, center, outer_radius, inner_radius, start_angle, start_angle + angle
        )
        parts.append(
            f'<path d="{path}" fill="{_color(index)}" stroke="currentColor" stroke-width="0.5"/>'
        )
        start_angle += angle

    row_height = 20
    legend_top = max(6.0, (size - len(display) * row_height) / 2.0)
    for index, (label, value) in enumerate(display):
        y = legend_top + index * row_height
        share = max(0.0, value) / total * 100.0
        shown = label if len(label) <= 26 else label[:25].rstrip() + "…"
        text = f"{shown} · {_fmt(max(0.0, value))} ({_fmt(share)}%)"
        parts.append(
            f'<rect x="{size + 8}" y="{_fmt(y)}" width="10" height="10" rx="2" '
            f'fill="{_color(index)}"/>'
            f'<text x="{size + 24}" y="{_fmt(y + 9)}" font-size="12" fill="currentColor">'
            f"{html.escape(text)}</text>"
        )

    return "".join(parts) + "</svg>"


def sparkline(values: Sequence[float], *, width: int = 240, height: int = 48) -> str:
    """Render a sparkline as a deterministic inline SVG."""
    title = "Sparkline"
    if not values:
        return _svg_open(width, height, title) + "</svg>"

    padding = 4
    plot_height = height - 2 * padding
    min_value = min(values)
    max_value = max(values)

    if len(values) == 1:
        x = width / 2.0
        if max_value == min_value:
            y = padding + plot_height / 2.0
        else:
            y = (
                padding
                + plot_height
                - (values[0] - min_value) / (max_value - min_value) * plot_height
            )
        return (
            _svg_open(width, height, title)
            + f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{_color(0)}"/></svg>'
        )

    points: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        x = padding + index / (len(values) - 1) * (width - 2 * padding)
        if max_value == min_value:
            y = padding + plot_height / 2.0
        else:
            y = padding + plot_height - (value - min_value) / (max_value - min_value) * plot_height
        points.append((x, y))

    path_d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points)
    return (
        _svg_open(width, height, title)
        + f'<path d="{path_d}" fill="none" stroke="currentColor" stroke-width="2"/>'
        + f'<circle cx="{points[-1][0]:.2f}" cy="{points[-1][1]:.2f}" r="2.5" '
        + f'fill="{_color(0)}"/></svg>'
    )


def stacked_bars(
    days: Sequence[str],
    series: Mapping[str, Sequence[float]],
    *,
    title: str,
    width: int = 720,
    height: int = 220,
) -> str:
    """Render stacked daily bars as a deterministic inline SVG."""
    if not days or not series:
        return _svg_open(width, height, title) + "</svg>"

    count = len(days)
    left = 40
    right = 20
    top = 30
    bottom = 40
    plot_width = width - left - right
    plot_height = height - top - bottom
    bar_width = (plot_width / count) * 0.6

    labels = sorted(series.keys())
    totals = [0.0] * count
    for label in labels:
        values = series[label]
        for index in range(count):
            if index < len(values):
                totals[index] += max(0.0, values[index])

    max_total = max(totals) if totals else 0.0
    if max_total <= 0.0:
        return _svg_open(width, height, title) + "</svg>"

    baseline_y = height - bottom
    parts = [_svg_open(width, height, title)]

    parts.append(
        f'<line x1="{left}" y1="{baseline_y}" x2="{width - right}" y2="{baseline_y}" '
        f'stroke="currentColor" stroke-width="1"/>'
    )
    parts.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{baseline_y}" '
        f'stroke="currentColor" stroke-width="1"/>'
    )

    for day_index, day in enumerate(days):
        x = left + (day_index + 0.5) * (plot_width / count) - bar_width / 2
        accumulated = 0.0
        for label_index, label in enumerate(labels):
            values = series[label]
            value = max(0.0, values[day_index]) if day_index < len(values) else 0.0
            bar_height = value / max_total * plot_height
            y = baseline_y - accumulated - bar_height
            if bar_height > 0:
                parts.append(
                    f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" '
                    f'height="{bar_height:.2f}" fill="{_color(label_index)}"/>'
                )
            accumulated += bar_height

        parts.append(
            f'<text x="{x + bar_width / 2:.2f}" y="{baseline_y + 18}" '
            f'text-anchor="middle" font-size="11" fill="currentColor">'
            f"{html.escape(str(day))}</text>"
        )

    return "".join(parts) + "</svg>"


def heat_grid(
    rows: Sequence[str],
    columns: Sequence[str],
    values: Mapping[tuple[str, str], float],
    *,
    title: str,
    cell: int = 26,
) -> str:
    """Render a heat grid as a deterministic inline SVG."""
    if not rows or not columns:
        width = max(cell * len(columns), 200)
        height = max(cell * len(rows), 120)
        return _svg_open(width, height, title) + "</svg>"

    left = 120
    top = 40
    width = left + len(columns) * cell + 10
    height = top + len(rows) * cell + 10

    max_value = max(values.values()) if values else 0.0
    parts = [_svg_open(width, height, title)]

    for column_index, column in enumerate(columns):
        x = left + column_index * cell + cell / 2
        parts.append(
            f'<text x="{x:.2f}" y="{top - 6}" text-anchor="start" font-size="11" '
            f'fill="currentColor" transform="rotate(45 {x:.2f} {top - 6:.2f})">'
            f"{html.escape(str(column))}</text>"
        )

    for row_index, row in enumerate(rows):
        y = top + row_index * cell + cell / 2
        parts.append(
            f'<text x="{left - 8}" y="{y:.2f}" text-anchor="end" '
            f'dominant-baseline="middle" font-size="11" fill="currentColor">'
            f"{html.escape(str(row))}</text>"
        )

    for row_index, row in enumerate(rows):
        for column_index, column in enumerate(columns):
            value = values.get((row, column), 0.0)
            opacity = 0.1 if max_value <= 0.0 else 0.1 + 0.9 * (value / max_value)
            x = left + column_index * cell
            y = top + row_index * cell
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{cell}" height="{cell}" '
                f'fill="{_color(0)}" fill-opacity="{_fmt(opacity)}" '
                f'stroke="currentColor" stroke-width="0.5"/>'
            )
            if value != 0.0:
                parts.append(
                    f'<text x="{x + cell / 2:.2f}" y="{y + cell / 2:.2f}" '
                    f'text-anchor="middle" dominant-baseline="middle" font-size="10" '
                    f'fill="currentColor">{_fmt(value)}</text>'
                )

    return "".join(parts) + "</svg>"
