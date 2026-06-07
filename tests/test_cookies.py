import requests

from yaseeker.core import load_cookies


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