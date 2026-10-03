"""Compare May 2026 baseline vs current v4-pro baseline."""
import json

new = json.load(open("evals/runs/pv-baseline-v4-pro-2026-07-08T124543Z.json", encoding="utf-8"))
old = json.load(open("evals/runs/pv-baseline-2026-05-07T181132Z.json", encoding="utf-8"))
nm, om = new["metrics"], old["metrics"]

print("=" * 65)
print(f"{'Metric':35s} {'May (old)':>12s} {'Now (v4-pro)':>12s}")
print("=" * 65)

comparisons = [
    ("Cases", "n_cases"),
    ("Errors", "n_errors"),
    ("Citation validity %", "citation_validity_rate"),
    ("Answered rate %", "answered_rate"),
    ("Expected-Yes Answered %", "expected_yes_answered_rate"),
    ("Avg citations/answer", "avg_citations_per_answer"),
    ("Avg chunks retrieved", "avg_chunks_retrieved"),
]

for label, key in comparisons:
    ov = om.get(key, 0)
    nv = nm.get(key, 0)
    if key.endswith("_rate"):
        print(f"{label:35s} {ov:>11.1%} {nv:>11.1%}")
    else:
        print(f"{label:35s} {ov:>11.2f} {nv:>11.2f}")

# latency
print(f"{'Latency p50':35s} {om.get('latency_p50',0):>10.2f}s {nm.get('latency_p50',0):>10.2f}s")
print(f"{'Latency p95':35s} {om.get('latency_p95',0):>10.2f}s {nm.get('latency_p95',0):>10.2f}s")

print()
print("--- Judge ---")
for label, key in [
    ("Supported %", "citation_supported_rate"),
    ("Partial %", "citation_partial_rate"),
    ("Not supported %", "citation_not_supported_rate"),
]:
    ov = om.get(key, 0)
    nv = nm.get(key, 0)
    print(f"{label:35s} {ov:>11.1%} {nv:>11.1%}")

print(f"\nOld: n_judgments={om.get('n_judgments','?')}")
print(f"New: n_judgments={nm.get('n_judgments','?')}")
