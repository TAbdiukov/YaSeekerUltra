import csv
import io
import sys

import pytest

import yasint.cli as cli


PUBLIC_ID = 'c48fhxw0qppa50289r5c9ku4k4'


def _no_lead_results(input_data):
    return [
        cli.OutputDataList(
            item,
            [cli.OutputData(item.value, {'platform': 'Music'}, None)],
            session_dir='',
        )
        for item in input_data
    ]


def _lead_results(input_data, session_dir=''):
    return [
        cli.OutputDataList(
            item,
            [cli.OutputData(item.value, {'platform': 'Music', 'username': item.value}, None)],
            session_dir=session_dir,
        )
        for item in input_data
    ]


class FakeProcessor:
    instances = []
    result_builder = _no_lead_results

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.input_data = None
        self.closed = False
        type(self).instances.append(self)

    async def process(self, input_data):
        self.input_data = input_data
        return type(self).result_builder(input_data)

    async def close(self):
        self.closed = True


@pytest.fixture()
def fake_processor(monkeypatch):
    FakeProcessor.instances = []
    FakeProcessor.result_builder = _no_lead_results
    monkeypatch.setattr(cli, 'Processor', FakeProcessor)
    return FakeProcessor


def test_run_exits_without_targets(monkeypatch, capsys, fake_processor):
    monkeypatch.setattr(sys, 'argv', ['yasint'])

    with pytest.raises(SystemExit) as exc_info:
        cli.run()

    assert exc_info.value.code == 1
    assert fake_processor.instances == []
    assert 'There are no targets to check!' in capsys.readouterr().out


def test_run_processes_positional_targets_and_closes_processor(monkeypatch, capsys, fake_processor):
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'yasint',
            '--no-progressbar',
            '--no-color',
            '--proxy',
            'socks5://127.0.0.1:1080',
            '--cookie-jar-file',
            'cookies.txt',
            'login',
            PUBLIC_ID,
        ],
    )

    cli.run()

    assert len(fake_processor.instances) == 1
    processor = fake_processor.instances[0]
    assert processor.kwargs == {
        'no_progressbar': True,
        'no_color': True,
        'proxy': 'socks5://127.0.0.1:1080',
        'cookie_file': 'cookies.txt',
    }
    assert [(i.value, i.identifier_type) for i in processor.input_data] == [
        ('login', 'username'),
        (PUBLIC_ID, 'yandex_public_id'),
    ]
    assert processor.closed is True

    out = capsys.readouterr().out
    assert 'Target: login (username)' in out
    assert f'Target: {PUBLIC_ID} (yandex_public_id)' in out
    assert out.count('Leads found: 0') == 2
    assert 'Total leads found: 0' in out


def test_run_reads_targets_from_stdin(monkeypatch, fake_processor):
    monkeypatch.setattr(sys, 'argv', ['yasint', '--targets-from-stdin', '--silent', '--no-progressbar'])
    monkeypatch.setattr(sys, 'stdin', io.StringIO('alpha\nbeta@yandex.ru\n'))

    cli.run()

    processor = fake_processor.instances[0]
    assert [(i.value, i.identifier_type) for i in processor.input_data] == [
        ('alpha', 'username'),
        ('beta', 'username'),
    ]
    assert processor.closed is True


def test_run_reads_target_list_and_writes_requested_reports(monkeypatch, capsys, tmp_path, fake_processor):
    target_file = tmp_path / 'targets.txt'
    txt_file = tmp_path / 'report.txt'
    csv_file = tmp_path / 'report.csv'
    target_file.write_text('login\nperson@yandex.ru\n', encoding='utf-8')
    fake_processor.result_builder = _lead_results
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'yasint',
            '--target-list',
            str(target_file),
            '--silent',
            '--no-progressbar',
            '-oT',
            str(txt_file),
            '-oC',
            str(csv_file),
        ],
    )

    cli.run()

    processor = fake_processor.instances[0]
    assert [i.value for i in processor.input_data] == ['login', 'person']

    out = capsys.readouterr().out
    assert 'Target:' not in out
    assert f'Results were saved to file {csv_file}' in out
    assert f'Results were saved to file {txt_file}' in out

    text = txt_file.read_text()
    assert 'Target: login (username)' in text
    assert 'Target: person (username)' in text
    assert 'Leads found: 1' in text
    assert 'Requests:' in text
    assert 'Music: GET https://music.yandex.ru/handlers/library.jsx?owner=login' in text

    with csv_file.open(newline='') as f:
        rows = list(csv.DictReader(f))

    assert [row['Target'] for row in rows] == ['login (username)', 'person (username)']
    assert [row['Leads Found'] for row in rows] == ['Yes', 'Yes']
    assert [row['Username'] for row in rows] == ['login', 'person']


def test_run_writes_auxiliary_reports_for_session_outputs(monkeypatch, capsys, tmp_path, fake_processor):
    session_dir = tmp_path / 'reports' / 'session'
    session_dir.mkdir(parents=True)

    def session_results(input_data):
        return _lead_results(input_data, session_dir=str(session_dir))

    fake_processor.result_builder = session_results
    monkeypatch.setattr(sys, 'argv', ['yasint', '--no-progressbar', '--no-color', 'login'])

    cli.run()

    aux_txt = session_dir / 'auxiliary_report.txt'
    aux_csv = session_dir / 'auxiliary_report.csv'
    assert aux_txt.exists()
    assert aux_csv.exists()
    assert f'Reports session: {session_dir}' in aux_txt.read_text()

    out = capsys.readouterr().out
    assert f'Reports session: {session_dir}' in out
    assert f'Results were saved to file {aux_txt}' in out
    assert f'Results were saved to file {aux_csv}' in out