import json
from pathlib import Path


def _to_norm(v):
    if v is None:
        return 0.0
    f = float(v)
    if f > 1.0:
        f = f / 100.0
    return max(0.0, min(1.0, f))


def main():
    root = Path('d:/jarvis')
    final_report_path = root / 'temp/gap_closure/final_report.json'
    round_report = root / 'temp/gap_closure/round_5.json'
    if final_report_path.exists():
        try:
            final_payload = json.loads(final_report_path.read_text(encoding='utf-8'))
            round_idx = int(final_payload.get('rounds_executed') or 0)
            if round_idx > 0:
                candidate = root / f'temp/gap_closure/round_{round_idx}.json'
                if candidate.exists():
                    round_report = candidate
        except Exception:
            pass
    if not round_report.exists():
        round_report = root / 'temp/gap_closure/round_1.json'
    if not round_report.exists():
        print(json.dumps({'ok': False, 'reason': 'missing_round_report'}, ensure_ascii=False))
        return 1

    payload = json.loads(round_report.read_text(encoding='utf-8'))
    scores = payload.get('scores', {})
    normalized_groups = {k: _to_norm(v) for k, v in (scores.get('group_scores', {}) or {}).items()}
    weighted_average = round(sum(normalized_groups.values()) / max(1, len(normalized_groups)), 4)

    critical_gaps = int(scores.get('critical_gap_count') or 0)
    major_gaps = int(scores.get('major_gap_count') or 0)
    approval = normalized_groups.get('approval_sandbox_policy', 0.0)
    benchmark = normalized_groups.get('benchmark_regression', 0.0)
    operator = normalized_groups.get('operator_quality_surface', 0.0)

    demo_report_path = root / 'temp/gap_closure/north_star_demo_report.json'
    demo_pass_ratio = 0.0
    if demo_report_path.exists():
        dr = json.loads(demo_report_path.read_text(encoding='utf-8'))
        demo_pass_ratio = (float(dr.get('passed_count') or 0.0) / max(1.0, float(dr.get('total') or 0.0)))

    passed = (
        weighted_average >= 0.90
        and critical_gaps == 0
        and major_gaps <= 3
        and approval >= 0.85
        and benchmark >= 0.85
        and operator >= 0.80
        and demo_pass_ratio >= (2.0 / 3.0)
    )

    result = {
        'ok': True,
        'comparable_gate_passed': passed,
        'weighted_average_score': weighted_average,
        'critical_gaps': critical_gaps,
        'major_gaps': major_gaps,
        'approval_sandbox_policy': approval,
        'benchmark_regression': benchmark,
        'operator_quality_surface': operator,
        'north_star_demo_pass_ratio': round(demo_pass_ratio, 4),
        'group_scores': normalized_groups,
        'status': 'PASSED' if passed else 'NOT PASSED',
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
