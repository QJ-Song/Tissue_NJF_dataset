#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


DEFAULT_CALIBRATION = Path("tissue_dataset_v0/outputs/liver_surface_scale_calibration/summary.json")
DEFAULT_LINEARIY = Path("tissue_dataset_v0/outputs/liver_surface_linearity_diagnostic/summary_calibrated_150mm.json")
DEFAULT_SCENE_LINEARIY = Path("tissue_dataset_v0/outputs/liver_surface_linearity_diagnostic/summary_extended.json")
DEFAULT_OUTPUT = Path("tissue_dataset_v0/outputs/liver_surface_visualization/report.html")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render liver surface-collision calibration/linearity diagnostics as HTML.")
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--linearity", type=Path, default=DEFAULT_LINEARIY)
    parser.add_argument("--scene-linearity", type=Path, default=DEFAULT_SCENE_LINEARIY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--linearity-threshold", type=float, default=0.10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    calibration = load_json(args.calibration)
    linearity = load_json(args.linearity)
    scene_linearity = load_json(args.scene_linearity) if args.scene_linearity.exists() else None
    report = render_report(calibration, linearity, scene_linearity, threshold=float(args.linearity_threshold))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote liver surface diagnostic report: {args.output}")
    return 0


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def render_report(
    calibration: dict[str, Any],
    linearity: dict[str, Any],
    scene_linearity: dict[str, Any] | None,
    *,
    threshold: float,
) -> str:
    mesh = calibration["mesh"]
    scale = calibration["scale"]
    target = calibration["target"]
    bbox = mesh["size_xyz_scene_units"]
    cards = [
        ("Target long axis", f"{target['long_axis_mm']:.1f} mm"),
        ("mm / scene unit", f"{scale['mm_per_scene_unit']:.4f}"),
        ("scene units / mm", f"{scale['scene_units_per_mm']:.8f}"),
        ("Surface vertices", str(mesh["vertex_count"])),
    ]

    calibrated_cases = linearity.get("cases", [])
    calibrated_rows = linearity.get("linearity", [])
    scene_rows = [] if scene_linearity is None else scene_linearity.get("linearity", [])

    body = f"""
    <section class="grid cards">{''.join(render_card(title, value) for title, value in cards)}</section>
    <section class="panel">
      <h2>Mesh Scale Calibration</h2>
      <p>{esc(mesh['name'])}: bounding box long-axis calibration using target liver length {target['long_axis_mm']:.1f} mm.</p>
      {bar_chart(
        labels=['x', 'y', 'z'],
        values=[float(v) for v in bbox],
        title='Mesh Bounding Box (scene units)',
        unit='scene units',
        color='#2b7a78',
      )}
      {depth_conversion_table(calibration.get('converted_local_linear_depths', []))}
    </section>
    <section class="panel">
      <h2>Calibrated Physical-mm Local Linearity</h2>
      <p>These depths use scene_units_per_mm={scale['scene_units_per_mm']:.8f}. The dashed line marks the {threshold:.0%} local-linearity threshold.</p>
      {linearity_chart(calibrated_rows, threshold=threshold, title='Relative Scale Error vs Physical Depth')}
      {response_chart(calibrated_cases, title='Response Norm vs Physical Depth')}
      {linearity_table(calibrated_rows)}
    </section>
    """
    if scene_linearity is not None:
        body += f"""
        <section class="panel">
          <h2>Uncalibrated Scene-unit Sweep</h2>
          <p>This is useful for checking the raw SOFA scene-unit boundary before physical scale interpretation.</p>
          {linearity_chart(scene_rows, threshold=threshold, title='Relative Scale Error vs Scene-unit Depth')}
          {linearity_table(scene_rows)}
        </section>
        """
    return html_page(body)


def html_page(body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Liver Surface Collision Diagnostics</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172026;
      --muted: #5d6970;
      --line: #d6dde1;
      --panel: #ffffff;
      --bg: #f4f7f8;
      --accent: #2b7a78;
      --warn: #b45309;
      --bad: #b91c1c;
    }}
    body {{
      margin: 0;
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    header {{
      padding: 28px 36px 16px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 24px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    p {{
      color: var(--muted);
      margin: 0 0 14px;
    }}
    main {{
      padding: 24px 36px 44px;
      max-width: 1120px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }}
    .card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .card {{
      padding: 14px 16px;
    }}
    .card .label {{
      color: var(--muted);
      font-size: 12px;
    }}
    .card .value {{
      font-size: 20px;
      font-weight: 650;
      margin-top: 4px;
    }}
    .panel {{
      padding: 18px;
      margin-top: 16px;
    }}
    .chart {{
      width: 100%;
      max-width: 820px;
      height: auto;
      display: block;
      margin: 10px 0 16px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin-top: 10px;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 7px;
      text-align: right;
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
    }}
    .keep {{ color: #166534; font-weight: 600; }}
    .reject {{ color: var(--bad); font-weight: 600; }}
  </style>
</head>
<body>
  <header>
    <h1>Liver Surface Collision Diagnostics</h1>
    <p>Calibration and local-linearity visualization for the standalone SOFA official-liver surface-collision scene.</p>
  </header>
  <main>{body}</main>
</body>
</html>
"""


def render_card(title: str, value: str) -> str:
    return f'<article class="card"><div class="label">{esc(title)}</div><div class="value">{esc(value)}</div></article>'


def bar_chart(labels: list[str], values: list[float], *, title: str, unit: str, color: str) -> str:
    width, height = 760, 270
    margin_left, margin_bottom, margin_top = 62, 48, 38
    plot_width = width - margin_left - 24
    plot_height = height - margin_top - margin_bottom
    maximum = max(values) if values else 1.0
    bar_gap = 24
    bar_width = (plot_width - bar_gap * (len(values) - 1)) / max(len(values), 1)
    parts = [
        svg_open(width, height),
        f'<text x="{margin_left}" y="24" font-size="16" font-weight="650">{esc(title)}</text>',
        axis_lines(width, height, margin_left, margin_bottom, margin_top),
    ]
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        x = margin_left + index * (bar_width + bar_gap)
        bar_height = plot_height * value / maximum
        y = margin_top + plot_height - bar_height
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{color}"/>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{height - 22}" text-anchor="middle" font-size="12">{esc(label)}</text>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" font-size="12">{value:.3f}</text>')
    parts.append(f'<text x="16" y="{margin_top + 16}" font-size="12" fill="#5d6970">{esc(unit)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def linearity_chart(rows: list[dict[str, Any]], *, threshold: float, title: str) -> str:
    points = [(float(row["depth_mm"]), float(row["relative_scale_error"])) for row in rows]
    return scatter_chart(
        points,
        title=title,
        x_label="depth",
        y_label="relative scale error",
        threshold=threshold,
        value_format="{:.3f}",
    )


def response_chart(cases: list[dict[str, Any]], *, title: str) -> str:
    points = [(float(case["depth_mm"]), float(case["response_norm"])) for case in cases]
    return scatter_chart(
        points,
        title=title,
        x_label="depth",
        y_label="response norm",
        threshold=None,
        value_format="{:.2f}",
    )


def scatter_chart(
    points: list[tuple[float, float]],
    *,
    title: str,
    x_label: str,
    y_label: str,
    threshold: float | None,
    value_format: str,
) -> str:
    width, height = 760, 300
    ml, mb, mt, mr = 62, 50, 38, 24
    pw, ph = width - ml - mr, height - mt - mb
    if not points:
        return f"<p>No data available for {esc(title)}.</p>"
    x_max = max(x for x, _ in points) * 1.12
    y_max = max(y for _, y in points)
    if threshold is not None:
        y_max = max(y_max, threshold)
    y_max *= 1.18
    y_max = y_max or 1.0

    def sx(x: float) -> float:
        return ml + pw * x / x_max

    def sy(y: float) -> float:
        return mt + ph - ph * y / y_max

    parts = [
        svg_open(width, height),
        f'<text x="{ml}" y="24" font-size="16" font-weight="650">{esc(title)}</text>',
        axis_lines(width, height, ml, mb, mt),
        f'<text x="{width / 2:.1f}" y="{height - 8}" text-anchor="middle" font-size="12" fill="#5d6970">{esc(x_label)}</text>',
        f'<text x="14" y="{mt + 24}" font-size="12" fill="#5d6970">{esc(y_label)}</text>',
    ]
    if threshold is not None:
        y = sy(threshold)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{width - mr}" y2="{y:.1f}" stroke="#b45309" stroke-dasharray="6 5"/>')
        parts.append(f'<text x="{width - mr - 4}" y="{y - 6:.1f}" text-anchor="end" font-size="12" fill="#b45309">{threshold:.0%}</text>')
    polyline = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in points)
    parts.append(f'<polyline points="{polyline}" fill="none" stroke="#2b7a78" stroke-width="2.5"/>')
    for x, y in points:
        parts.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4.5" fill="#2b7a78"/>')
        parts.append(f'<text x="{sx(x):.1f}" y="{sy(y) - 9:.1f}" text-anchor="middle" font-size="11">{value_format.format(y)}</text>')
        parts.append(f'<text x="{sx(x):.1f}" y="{height - 28}" text-anchor="middle" font-size="11">{x:g}</text>')
    parts.append("</svg>")
    return "".join(parts)


def axis_lines(width: int, height: int, ml: int, mb: int, mt: int) -> str:
    x2 = width - 24
    y = height - mb
    return (
        f'<line x1="{ml}" y1="{y}" x2="{x2}" y2="{y}" stroke="#9aa6ad"/>'
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{y}" stroke="#9aa6ad"/>'
    )


def depth_conversion_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    body = "".join(
        f"<tr><td>{row['scene_units']:.3f}</td><td>{row['mm']:.3f}</td></tr>"
        for row in rows
    )
    return f"<table><thead><tr><th>Scene units</th><th>Calibrated mm</th></tr></thead><tbody>{body}</tbody></table>"


def linearity_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No linearity rows available.</p>"
    body = []
    for row in rows:
        cls = "keep" if row.get("recommendation") == "keep" else "reject"
        body.append(
            "<tr>"
            f"<td>{row['reference_depth_mm']:g} -> {row['depth_mm']:g}</td>"
            f"<td>{row['scale_factor']:.3f}</td>"
            f"<td>{row['relative_scale_error']:.5f}</td>"
            f"<td>{row['cosine_with_scaled_reference']:.5f}</td>"
            f'<td class="{cls}">{esc(row["recommendation"])}</td>'
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Depth</th><th>Scale</th><th>Relative error</th>"
        "<th>Cosine</th><th>Decision</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def svg_open(width: int, height: int) -> str:
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" xmlns="http://www.w3.org/2000/svg">'


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
