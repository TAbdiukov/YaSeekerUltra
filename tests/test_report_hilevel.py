import csv

from yasint.core import OutputData, OutputDataList
from yasint.report import CSVOutput, PlainOutput, TXTOutput


def _mixed_report_data(tmp_path):
    login_session = str(tmp_path / 'reports' / 'login_session')
    empty_session = str(tmp_path / 'reports' / 'empty_session')

    return [
        OutputDataList(
            'login (username)',
            [
                OutputData(
                    'login',
                    {
                        'platform': 'Music',
                        'username': 'login',
                        'yandex_uid': '266797119',
                    },
                    None,
                ),
                OutputData('login', {'platform': 'Bugbounty'}, None),
            ],
            session_dir=login_session,
        ),
        OutputDataList(
            'empty (username)',
            [OutputData('empty', {'platform': 'Music'}, None)],
            session_dir=empty_session,
        ),
    ], login_session, empty_session


def test_plain_output_summarizes_leads_no_leads_and_requests(tmp_path):
    data, login_session, empty_session = _mixed_report_data(tmp_path)

    text = PlainOutput(data, colored=False).put()

    assert f'Target: login (username)\nReports session: {login_session}\nLeads found: 1\n' in text
    assert 'Value: login\n' in text
    assert 'Platform: Music\n' in text
    assert 'Username: login\n' in text
    assert 'Yandex Uid: 266797119\n' in text

    assert f'Target: empty (username)\nReports session: {empty_session}\nLeads found: 0\n' in text
    assert 'No leads found.\n' in text
    assert 'Total leads found: 1\n' in text

    assert 'Requests:\n' in text
    assert 'Music: GET https://music.yandex.ru/handlers/library.jsx?owner=login\n' in text
    assert 'Bugbounty: GET' not in text
    assert 'owner=empty' not in text


def test_txt_output_writes_the_same_uncoloured_text_as_plain_output(tmp_path):
    data, _, _ = _mixed_report_data(tmp_path)
    filename = tmp_path / 'report.txt'

    message = TXTOutput(data, filename=str(filename)).put()

    assert message == f'Results were saved to file {filename}'
    assert filename.read_text() == PlainOutput(data, colored=False).put()


def test_csv_output_writes_lead_rows_and_no_lead_placeholder_rows(tmp_path):
    data, login_session, empty_session = _mixed_report_data(tmp_path)
    filename = tmp_path / 'report.csv'

    message = CSVOutput(data, filename=str(filename)).put()

    assert message == f'Results were saved to file {filename}'

    with filename.open(newline='') as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert {'Target', 'Reports Session', 'Leads Found', 'Value', 'Platform', 'Username', 'Yandex Uid'}.issubset(
        rows[0].keys()
    )

    lead_row = next(row for row in rows if row['Target'] == 'login (username)')
    assert lead_row['Reports Session'] == login_session
    assert lead_row['Leads Found'] == 'Yes'
    assert lead_row['Value'] == 'login'
    assert lead_row['Platform'] == 'Music'
    assert lead_row['Username'] == 'login'
    assert lead_row['Yandex Uid'] == '266797119'

    no_lead_row = next(row for row in rows if row['Target'] == 'empty (username)')
    assert no_lead_row['Reports Session'] == empty_session
    assert no_lead_row['Leads Found'] == 'No'
    assert no_lead_row['Value'] == ''
    assert no_lead_row['Platform'] == ''
    assert no_lead_row['Username'] == ''
    assert no_lead_row['Yandex Uid'] == ''


def test_plain_output_request_summary_falls_back_to_extracted_url_once_for_unknown_platform():
    data = [
        OutputDataList(
            'custom (username)',
            [
                OutputData(
                    'custom',
                    {
                        'platform': 'Custom Service',
                        'URL': 'https://example.test/profile',
                        'URL_secondary': 'https://example.test/raw',
                    },
                    None,
                ),
                OutputData(
                    'custom',
                    {
                        'platform': 'Custom Service',
                        'URL': 'https://example.test/profile',
                        'URL_secondary': 'https://example.test/raw',
                    },
                    None,
                ),
            ],
        )
    ]

    text = PlainOutput(data, colored=False).put()

    assert 'Total leads found: 2\n' in text
    assert text.count('Custom Service: GET https://example.test/raw\n') == 1