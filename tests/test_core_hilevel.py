import asyncio
from types import SimpleNamespace

import yaseeker.core as core


class FakeProgress:
    def __init__(self):
        self.total = 0
        self.refreshed = 0
        self.updates = []

    def refresh(self):
        self.refreshed += 1

    def update(self, value):
        self.updates.append(value)


def test_input_data_strips_email_domain_and_classifies_ids(capsys):
    public_id = 'c48fhxw0qppa50289r5c9ku4k4'

    username_input = core.InputData('login@yandex.ru')
    public_id_input = core.InputData(public_id)

    output = capsys.readouterr().out

    assert username_input.value == 'login'
    assert username_input.identifier_type == 'username'
    assert str(username_input) == 'login (username)'

    assert public_id_input.value == public_id
    assert public_id_input.identifier_type == 'yandex_public_id'
    assert str(public_id_input) == f'{public_id} (yandex_public_id)'

    assert 'Identifier "login" recognized as a username' in output
    assert f'Identifier "{public_id}" recognized as a yandex_public_id' in output


def test_crawl_recurses_over_discovered_identifiers_once(monkeypatch):
    constructed = []

    class FakeUsername:
        @classmethod
        def validate_id(cls, name, identifier):
            return name == 'username'

        def __init__(self, identifier, cookies, session_recorder=None, progress=None):
            self.identifier = identifier
            self.sites_results = {}
            self.info = {}
            constructed.append(('username', identifier, cookies, session_recorder, progress))

        def collect(self):
            self.sites_results = {'music': {'username': self.identifier}}
            self.info = {
                'username': self.identifier,
                'yandex_public_id': 'public-identifier',
            }

    class FakePublicUserId:
        @classmethod
        def validate_id(cls, name, identifier):
            return name == 'yandex_public_id'

        def __init__(self, identifier, cookies, session_recorder=None, progress=None):
            self.identifier = identifier
            self.sites_results = {}
            self.info = {}
            constructed.append(('public', identifier, cookies, session_recorder, progress))

        def collect(self):
            self.sites_results = {'reviews': {'id': self.identifier}}
            self.info = {'yandex_public_id': self.identifier}

    class FakeMessengerGuid:
        @classmethod
        def validate_id(cls, name, identifier):
            return False

    monkeypatch.setattr(core, 'YaUsername', FakeUsername)
    monkeypatch.setattr(core, 'YaPublicUserId', FakePublicUserId)
    monkeypatch.setattr(core, 'YaMessengerGuid', FakeMessengerGuid)

    cookies = {'session': 'cookie'}

    output = core.crawl(
        {'username': 'alice'},
        {},
        cookies=cookies,
        session_recorder='recorder',
        progress='progress',
    )

    assert output == {
        'alice': {'music': {'username': 'alice'}},
        'public-identifier': {'reviews': {'id': 'public-identifier'}},
    }
    assert constructed == [
        ('username', 'alice', cookies, 'recorder', 'progress'),
        ('public', 'public-identifier', cookies, 'recorder', 'progress'),
    ]


def test_aggregator_collects_sites_aggregates_info_and_tracks_progress():
    class DemoAggregator(core.IdTypeInfoAggregator):
        def get_music_info(self):
            self._finish_url_hit()
            return {'username': self.identifier, 'shared': 'music'}

        def get_reviews_info(self):
            self._finish_url_hit()
            return {'yandex_public_id': 'public-identifier', 'shared': 'reviews'}

    progress = FakeProgress()
    aggregator = DemoAggregator('login', cookies={}, progress=progress)

    aggregator.collect()

    assert progress.total == 2
    assert progress.refreshed == 1
    assert progress.updates == [1, 1]
    assert aggregator.sites_results == {
        'music': {'username': 'login', 'shared': 'music'},
        'reviews': {'yandex_public_id': 'public-identifier', 'shared': 'reviews'},
    }
    assert aggregator.info == {
        'username': 'login',
        'shared': {'music', 'reviews'},
        'yandex_public_id': 'public-identifier',
    }


def test_simple_get_info_request_records_response_and_returns_extracted_data(monkeypatch):
    class FakeRecorder:
        def __init__(self):
            self.responses = []

        def save_response(self, method, url, response):
            self.responses.append((method, url, response))

    calls = []
    response = SimpleNamespace(text='response body')

    def fake_get(url, headers, cookies):
        calls.append({'url': url, 'headers': headers, 'cookies': cookies})
        return response

    def fake_extract(text):
        assert text == 'response body'
        return {'username': 'login'}

    monkeypatch.setattr(core.requests, 'get', fake_get)
    monkeypatch.setattr(core, 'extract', fake_extract)

    cookies = {'session': 'cookie'}
    recorder = FakeRecorder()
    progress = FakeProgress()
    aggregator = core.IdTypeInfoAggregator(
        'login',
        cookies=cookies,
        session_recorder=recorder,
        progress=progress,
    )

    info = aggregator.simple_get_info_request(
        'https://example.test/api/login',
        headers_updates={'X-Test': 'yes'},
        orig_url='https://example.test/profile/login',
    )

    assert info == {
        'username': 'login',
        'URL': 'https://example.test/profile/login',
        'URL_secondary': 'https://example.test/api/login',
    }
    assert calls[0]['url'] == 'https://example.test/api/login'
    assert calls[0]['cookies'] is cookies
    assert calls[0]['headers']['User-Agent'] == core.HEADERS['User-Agent']
    assert calls[0]['headers']['X-Test'] == 'yes'
    assert recorder.responses == [('GET', 'https://example.test/api/login', response)]
    assert progress.updates == [1]


def test_processor_request_builds_session_output_from_crawl(monkeypatch, tmp_path):
    class FakeSessionRecorder:
        def __init__(self, root, target):
            assert root == core.REPORTS_DIRNAME
            self.timestamp = '20260101T000000Z'
            self.session_dir = tmp_path / root / target
            self.session_dir.mkdir(parents=True)

    def fake_crawl(identifier, output, cookies=None, checked_values=None, session_recorder=None, progress=None):
        assert identifier == {'username': 'login'}
        assert output == {}
        assert checked_values is None
        assert cookies == {'session': 'cookie'}
        assert isinstance(session_recorder, FakeSessionRecorder)
        assert progress is None

        return {
            'login': {
                'music': {
                    'username': 'login',
                    'image': 'https://avatars.test/islands-200/photo.jpg',
                },
                'reviews': {},
            },
            'public-id': {
                'zen': {
                    'fullname': 'Alice Example',
                },
            },
        }

    monkeypatch.setattr(core, 'SessionRecorder', FakeSessionRecorder)
    monkeypatch.setattr(core, 'crawl', fake_crawl)

    processor = core.Processor.__new__(core.Processor)
    processor.no_progressbar = True
    processor.cookies = {'session': 'cookie'}
    input_data = SimpleNamespace(value='login', identifier_type='username')

    output = asyncio.run(processor.request(input_data))

    assert output.input_data is input_data
    assert output.session_dir == str((tmp_path / core.REPORTS_DIRNAME / 'login').resolve())
    assert [r.value for r in output.results] == ['login', 'login', 'public-id']
    assert [r.platform for r in output.results] == ['Music', 'Reviews', 'Zen']
    assert [r.error for r in output.results] == [None, None, None]
    assert output.results[0].image == 'https://avatars.test/islands-300/photo.jpg'
    assert output.results[1].fields == ['value', 'platform']
    assert output.results[2].fullname == 'Alice Example'