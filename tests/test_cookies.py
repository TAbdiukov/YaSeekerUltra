import asyncio

import requests

from yaseeker.core import Processor, load_cookies


def _write_cookie_file(cookie_file):
    cookie_file.write_text(
        '# Netscape HTTP Cookie File\n'
        '.yandex.ru\tTRUE\t/\tFALSE\t2147483647\tyandex_cookie\t1\n',
        encoding='utf-8',
    )


def _processor_cookie_output(cookie_file, no_color, capsys):
    async def _run():
        processor = Processor(cookie_file=str(cookie_file), no_color=no_color)
        try:
            return capsys.readouterr().out
        finally:
            await processor.close()

    return asyncio.run(_run())


def test_load_cookies_preserves_domain_scoping(tmp_path):
    cookie_file = tmp_path / 'cookies.txt'
    cookie_file.write_text(
        '# Netscape HTTP Cookie File\n'
        '.yandex.ru\tTRUE\t/\tFALSE\t2147483647\tyandex_cookie\t1\n'
        'example.com\tFALSE\t/\tFALSE\t2147483647\texample_cookie\t2\n',
        encoding='utf-8',
    )

    cookies = load_cookies(str(cookie_file))
    request = requests.Request(
        'GET',
        'https://yandex.ru/collections/api/users/test',
        cookies=cookies,
    )

    prepared = requests.Session().prepare_request(request)

    assert prepared.headers.get('Cookie') == 'yandex_cookie=1'


def test_processor_reports_loaded_cookies_in_colour(tmp_path, capsys):
    cookie_file = tmp_path / 'cookies.txt'
    _write_cookie_file(cookie_file)

    output = _processor_cookie_output(cookie_file, no_color=False, capsys=capsys)

    assert f'Cookies loaded from {cookie_file} for queried domains: 1 cookie.' in output
    assert '\x1b[' in output


def test_processor_loaded_cookie_message_respects_no_color(tmp_path, capsys):
    cookie_file = tmp_path / 'cookies.txt'
    _write_cookie_file(cookie_file)

    output = _processor_cookie_output(cookie_file, no_color=True, capsys=capsys)

    assert output == f'Cookies loaded from {cookie_file} for queried domains: 1 cookie.\n'


def test_processor_reports_when_loaded_cookies_do_not_match_queried_domains(tmp_path, capsys):
    cookie_file = tmp_path / 'cookies.txt'
    cookie_file.write_text(
        '# Netscape HTTP Cookie File\n'
        'example.com\tFALSE\t/\tFALSE\t2147483647\texample_cookie\t2\n',
        encoding='utf-8',
    )

    output = _processor_cookie_output(cookie_file, no_color=True, capsys=capsys)

    assert output == f'Cookies loaded from {cookie_file}, but none match queried domains.\n'