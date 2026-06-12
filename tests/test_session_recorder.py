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
