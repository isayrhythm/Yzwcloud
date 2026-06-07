from __future__ import annotations

from pathlib import Path

from yzwcloud.analyses.wgcna import write_wgcna_html


def test_wgcna_html_reserves_label_space_for_plots(tmp_path: Path) -> None:
    output = tmp_path / "wgcna.html"
    payload = {
        "summary": {
            "module_count": 3,
            "assigned_gene_count": 999,
            "selected_gene_count": 999,
            "sample_count": 24,
            "soft_power": 6,
        },
        "conditions": ["cancer", "long_condition_name", "normal"],
        "modules": [
            {
                "module": "MEturquoise_with_a_long_label",
                "gene_count": 431,
                "color_hex": "#40e0d0",
                "top_condition": "normal",
                "top_correlation": 0.84,
                "top_hubs": [{"gene": "GENE1"}],
            },
            {
                "module": "MEbrown_with_a_long_label",
                "gene_count": 314,
                "color_hex": "#a52a2a",
                "top_condition": "cancer",
                "top_correlation": -0.69,
                "top_hubs": [{"gene": "GENE2"}],
            },
            {
                "module": "MEyellow",
                "gene_count": 212,
                "color_hex": "#ffff00",
                "top_condition": "long_condition_name",
                "top_correlation": 0.70,
                "top_hubs": [],
            },
        ],
        "module_trait": [
            {"module": "MEturquoise_with_a_long_label", "condition": "normal", "correlation": 0.84, "p_value": 0.001},
            {"module": "MEbrown_with_a_long_label", "condition": "cancer", "correlation": -0.69, "p_value": 0.01},
        ],
        "soft_threshold": [{"power": 6, "scale_free_fit": 0.9}],
    }

    write_wgcna_html(output, payload)

    html = output.read_text(encoding="utf-8")
    assert "function maxTextWidth" in html
    assert "function fitText" in html
    assert "function canvasPanelWidth" in html
    assert ".panel{padding:14px;border:1px solid #d9e5ec;border-radius:16px;background:white;overflow:hidden}" in html
    assert "canvas{display:block;width:100%;max-width:100%;height:auto;margin:0 auto}" in html
    assert "const panelWidth = canvasPanelWidth(canvas, 680)" in html
    assert "canvas.width = panelWidth" in html
    assert "const contentStart = Math.max(10, Math.floor((panelWidth - contentWidth) / 2))" in html
    assert "const panelWidth = canvasPanelWidth(canvas, 720)" in html
    assert "const barMax = Math.max(70, Math.floor((panelWidth - moduleLabelWidth - valueLabelWidth - 88) / 2))" in html
    assert "window.addEventListener('resize'" in html
