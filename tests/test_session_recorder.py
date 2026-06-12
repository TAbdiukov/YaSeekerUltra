import codecs
from types import SimpleNamespace

from yaseeker.core import SessionRecorder


def _fake_response(content, text_encoding):
    return SimpleNamespace(
        history=[],
        request=SimpleNamespace(method='GET', url='https://example.test/profile'),
        url='https://example.test/profile',
        reason='OK',
        status_code=200,
        headers={'Content-Type': 'text/html'},
        content=content,
        text=content.decode(text_encoding),
    )


def _fake_avatar_response(content, content_type):
    return SimpleNamespace(
        status_code=200,
        reason='OK',
        headers={'Content-Type': content_type},
        content=content,
    )


def _saved_html_bytes(tmp_path, content, text_encoding):
    recorder = SessionRecorder(str(tmp_path), 'target')
    recorder.save_response(
        'GET',
        'https://example.test/profile',
        _fake_response(content, text_encoding),
    )

    files = list(recorder.session_dir.glob('*.html'))

    assert len(files) == 1
    return files[0].read_bytes()


def test_html_response_body_bytes_are_not_reencoded(tmp_path):
    body = (
        '<html><head><meta charset="windows-1251"></head>'
        '<body>Привет мир Привет мир</body></html>'
    ).encode('windows-1251')

    saved = _saved_html_bytes(tmp_path, body, 'windows-1251')

    assert saved.endswith(body)
    assert 'Привет'.encode('utf-8') not in saved
    assert saved.decode('windows-1251').startswith('<!--\nRequest:')


def test_html_response_comment_uses_detected_multibyte_encoding(tmp_path):
    body = '<html><body>Привет мир Привет мир</body></html>'.encode('utf-16-le')

    saved = _saved_html_bytes(tmp_path, body, 'utf-16-le')

    assert saved.startswith('<!--\n'.encode('utf-16-le'))
    assert saved.endswith(body)
    assert saved.decode('utf-16-le').startswith('<!--\nRequest:')


def test_html_response_keeps_bom_at_file_start(tmp_path):
    body = codecs.BOM_UTF16_LE + '<html><body>Привет</body></html>'.encode('utf-16-le')

    saved = _saved_html_bytes(tmp_path, body, 'utf-16')

    assert saved.startswith(codecs.BOM_UTF16_LE)
    assert saved[len(codecs.BOM_UTF16_LE):].startswith('<!--\n'.encode('utf-16-le'))
    assert saved.endswith(body[len(codecs.BOM_UTF16_LE):])

def test_avatar_ignore_list_skips_realty_urls_and_default_islands_sizes(tmp_path, monkeypatch):
    avatar_body = b'avatar'
    downloaded_urls = []
    real_avatar_url = 'https://avatars.mds.yandex.net/get-yapic/63032/enc-test/islands-68'

    def fake_get(url, **kwargs):
        downloaded_urls.append(url)
        return _fake_avatar_response(avatar_body, 'image/jpeg')

    monkeypatch.setattr('yaseeker.core.requests.get', fake_get)

    body = (
        '<html><head><style>'
        '.avatar{background-image:url(https://avatars.mds.yandex.net/get-yapic/0/0-0/islands-200);'
        'background-repeat:no-repeat}'
        '</style></head><body>'
        f'<img alt="Аватар пользователя" src="{real_avatar_url}">'
        '<script>'
        'window.__data__ = "https:\\/\\/avatars.mds.yandex.net\\/get-realty-content\\/8111885\\/add.17347007366631ecde4f8d8\\/main";'
        'window.__data2__ = "https:\\/\\/avatars.mds.yandex.net\\/get-realty-offers\\/14819877\\/d9b50816-11d2-4dfa-a55a-56b2dec05fab\\/orig";'
        'window.__data3__ = "https:\\/\\/avatars.mds.yandex.net\\/get-verba\\/1540742\\/2a000001\\/islands-retina";'
        'window.__data4__ = "https:\\/\\/avatars.mds.yandex.net\\/get-yapic\\/0\\/0-0\\/islands-retina";'
        '</script>'
        '</body></html>'
    ).encode('utf-8')

    recorder = SessionRecorder(str(tmp_path), 'target')
    recorder.save_response(
        'GET',
        'https://example.test/profile',
        _fake_response(body, 'utf-8'),
    )

    avatar_files = list(recorder.session_dir.glob('*.avatar.jpg'))
    error_files = list(recorder.session_dir.glob('*.error.txt'))

    assert downloaded_urls == [real_avatar_url]
    assert len(avatar_files) == 1
    assert avatar_files[0].read_bytes() == avatar_body
    assert error_files == []
