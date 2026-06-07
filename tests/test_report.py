import csv

from yaseeker.core import OutputData, OutputDataList
from yaseeker.report import CSVOutput, PlainOutput


def test_plain_output_makes_no_leads_explicit(tmp_path):
    session_dir = str(tmp_path / 'reports' / 'session')
    data = [
        OutputDataList(
            'login (username)',
            [OutputData('login', {'platform': 'Music'}, None)],
            session_dir=session_dir,
        )
    ]

    text = PlainOutput(data, colored=False).put()

    assert f'Reports session: {session_dir}' in text
    assert 'Leads found: 0' in text
    assert 'No leads found.' in text
    assert 'Total leads found: 0' in text


def test_csv_output_makes_no_leads_explicit(tmp_path):
    session_dir = str(tmp_path / 'reports' / 'session')
    filename = tmp_path / 'report.csv'
    data = [
        OutputDataList(
            'login (username)',
            [OutputData('login', {'platform': 'Music'}, None)],
            session_dir=session_dir,
        )
    ]

    CSVOutput(data, filename=str(filename)).put()

    with filename.open(newline='') as f:
        rows = list(csv.DictReader(f))

    assert rows == [
        {
            'Target': 'login (username)',
            'Reports Session': session_dir,
            'Leads Found': 'No',
        }
    ]