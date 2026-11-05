"""Isolated batch acceptance using the supplied Separator and TL-B workbooks.

This checks software coverage/readiness and export integrity only. It does not
certify physical continuity, source formulas, code applicability, or fitness.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from evaluator.app_services import ProjectService


def evaluate_case(service, workbook, previous, current, label):
    source = service.add_source(workbook)
    source_id = source.sha256
    service.inspect(source_id)
    for sheet in dict.fromkeys((previous[0], current[0])):
        service.extract(source_id, sheet)
    comparison = service.workflow.compare(
        source_id, *previous, source_id, *current, label,
        'SOFTWARE ACCEPTANCE / physical continuity not certified',
        True, 'Acceptance test', 'Synthetic confirmation to exercise batch paths',
        expected_revision=service.workflow.revision(),
    )
    service.batch.prepare(comparison['id'], service.workflow.revision())
    preview = service.batch.preview(comparison['id'])
    result = service.batch.evaluate(
        comparison['id'], service.workflow.revision(),
        {
            'profile_sheet': preview['profile_sheet'],
            'confirm_records': True,
            'confirm_history': True,
            'confirm_conflicts': True,
        },
        preview['preview_token'],
    )
    current_rows = [row for row in result['rows'] if row['current_id']]
    assert len({row['current_id'] for row in current_rows}) == len(current_rows)
    assert result['status'] == 'DRAFT / NOT VALIDATED'
    assert all(row['outputs']['status'] == 'DRAFT / NOT VALIDATED' for row in result['rows'])
    return {
        'workbook': workbook.name,
        'sha256': source_id,
        'previous': list(previous),
        'current': list(current),
        'comparison_id': comparison['id'],
        'profile_sheet': preview['profile_sheet'],
        'source_records': len(preview['profiles']),
        'current_rows': len(current_rows),
        'preview_counts': preview['counts'],
        'output_counts': result['summary'],
        'issue_counts': dict(Counter(issue for row in result['rows'] for issue in row['issues'])),
        'rows': result['rows'],
    }


def run(destination: Path) -> dict:
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / 'project.sqlite').exists():
        raise ValueError('Choose a fresh isolated validation destination')
    workbooks = ROOT / 'sources' / 'workbooks'
    originals = {p.name: sha256(p.read_bytes()).hexdigest() for p in workbooks.glob('*')}
    service = ProjectService(destination)
    cases = [
        evaluate_case(
            service,
            workbooks / 'Separator-204 Inspection Report.xlsx',
            ('UT Aug-2024', 'current'),
            ('UT Jan 2026', 'current'),
            'Separator-204 / software acceptance',
        ),
        evaluate_case(
            service,
            workbooks / 'TL-B from SAG Gas MFD to GP.xlsx',
            ('10-2022', '10-2022'),
            ('UT 5-2025', '05-2025'),
            'TL-B / software acceptance',
        ),
    ]
    separator, pipeline = cases
    assert separator['current_rows'] == 37
    assert separator['preview_counts']['historical_ready'] == 29
    assert separator['output_counts']['current'] == 37
    assert separator['issue_counts'].get('PROFILE_CURRENT_CONFLICT', 0) > 0
    assert pipeline['current_rows'] == 81
    assert pipeline['source_records'] == 80
    assert pipeline['output_counts']['current'] == 81
    assert pipeline['output_counts']['life_evaluated'] > 0
    assert pipeline['output_counts']['interval_evaluated'] > 0
    assert pipeline['issue_counts'].get('HISTORY_DATE_REQUIRED', 0) == 19
    assert pipeline['issue_counts'].get('GOVERNING_MINIMUM_NOT_ESTABLISHED', 0) > 0

    archive_path = destination / 'batch-acceptance-export.zip'
    target = service.workflow.export_revision()
    archive_path.write_bytes(target.read_bytes())
    with zipfile.ZipFile(archive_path) as archive:
        batch_csv = archive.read('batch_evaluations.csv').decode('utf-8-sig')
        report = archive.read('summary.html').decode('utf-8')
        manifest = json.loads(archive.read('manifest.json'))
        assert 'Component batch evaluation' in report
        assert cases[0]['comparison_id'] in batch_csv
        assert cases[1]['comparison_id'] in batch_csv
        for name, digest in manifest['files'].items():
            assert sha256(archive.read(name)).hexdigest() == digest, name
    after = {p.name: sha256(p.read_bytes()).hexdigest() for p in workbooks.glob('*')}
    assert originals == after, 'Source workbook bytes changed during acceptance'
    evidence = {
        'purpose': 'Software-only actual-source batch acceptance; not engineering certification',
        'cases': cases,
        'export': str(archive_path),
        'export_revision': manifest['revision'],
        'source_hashes_before': originals,
        'source_hashes_after': after,
    }
    (destination / 'verification.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False))
    return evidence


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    result = run(args.destination)
    for case in result['cases']:
        print(case['workbook'], case['output_counts'])
    print(result['export'])
