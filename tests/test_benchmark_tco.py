"""
Unit tests for Total Cost of Ownership (TCO) & Break-Even Benchmark.
"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from benchmark_tco import (
    DEFAULT_CLOUD_MODELS,
    DEFAULT_HARDWARE,
    CloudModelPricing,
    HardwareProfile,
    TCOAnalyzer,
)


def test_hardware_monthly_cost():
    hw = HardwareProfile(
        name="Test 4090",
        hardware_type="capex_amortized",
        capex_usd=3600.0,
        amortization_months=36,
        electricity_watts=400.0,
        kwh_cost_usd=0.20,
    )
    # Capex: 3600 / 36 = $100/mo
    # Power: 400W * 730h / 1000 * 0.5 duty cycle = 146 kWh * $0.20 = $29.20
    # Total: $129.20
    monthly = hw.monthly_cost_usd()
    assert round(monthly, 2) == 129.20


def test_cloud_model_cost_per_query():
    model = CloudModelPricing(
        model_name="test-model",
        prompt_usd_per_1m=1.00,
        cached_prompt_usd_per_1m=0.50,
        completion_usd_per_1m=4.00,
    )
    # 10,000 prompt tokens (30% cached = 3,000 cached @ $0.50/M; 7,000 uncached @ $1.00/M)
    # 1,000 completion tokens @ $4.00/M
    # Cached: 3,000 / 1M * 0.50 = $0.0015
    # Uncached: 7,000 / 1M * 1.00 = $0.0070
    # Comp: 1,000 / 1M * 4.00 = $0.0040
    # Total: $0.0125
    cost = model.cost_per_query(prompt_tokens=10000, completion_tokens=1000, cache_hit_rate=0.30)
    assert round(cost, 4) == 0.0125


def test_tco_break_even_analysis():
    hw = DEFAULT_HARDWARE["rtx_4090_local"]
    analysis = TCOAnalyzer.analyze(
        hardware=hw,
        prompt_tokens=1500,
        completion_tokens=500,
        cache_hit_rate=0.30,
    )

    assert analysis.hardware_monthly_cost > 0
    assert "gpt-4o" in analysis.cloud_comparisons
    assert "o3-mini" in analysis.cloud_comparisons

    o3_comp = analysis.cloud_comparisons["o3-mini"]
    assert o3_comp["break_even_queries_per_day"] > 0
    assert o3_comp["break_even_queries_per_month"] > 0

    # Markdown generation check
    md = analysis.to_markdown()
    assert "# Total Cost of Ownership (TCO)" in md
    assert "The Hybrid Speculative Advantage" in md
    assert "`o3-mini`" in md
