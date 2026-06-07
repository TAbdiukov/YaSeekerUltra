# YaSeeker

<p align="center">
  <img src="./logo.jpg" />
</p>

## Description

YaSeeker - an OSINT tool to get info about any Yandex account using email or login.

It can find:
- Fullname
- Photo
- Gender
- Yandex UID
- Yandex Public ID
- Linked social accounts
- Activity (count of reviews, comments; subscribers and subscriptions)
- Account features (is it verified, banned, deleted, etc.)

Checked Yandex services: Music, Collections, Bugbounty, Reviews, Q (Znatoki), O (Classified), Zen, Market, Messenger.

## Installation

Python 3.6+ and pip are required.

    pip3 install -r requirements.txt

## Usage

```bash
$ python3 run.py login
# or
$ yaseeker login
```

YaSeeker now performs deep artifact pivots automatically. If one artifact reveals another queryable artifact (for example a username reveals a Yandex public ID, which then reveals a messenger GUID), the new artifact is queued and queried in the same run. Console output starts with a color-coded artifact tracker and then prints the full per-platform results at the end.

## Example

```bash
$ yaseeker login
Target: login (username)
Artifacts discovered: 3
Artifacts:
  1) seed queried depth=0 username: login
  2) auto queried depth=1 yandex_public_id: c48fhxw0qppa50289r5c9ku4k4
      via username: login -> Collections Api.yandex_public_id
  3) auto queried depth=2 yandex_messenger_guid: 00000000-0000-0000-0000-000000000000
      via yandex_public_id: c48fhxw0qppa50289r5c9ku4k4 -> Messenger.yandex_messenger_guid

Detailed results:
1) username: login
   Platforms with data: 4/5
   1) Collections Api [found]
      URL: https://yandex.ru/collections/user/login/
      Yandex Public Id: c48fhxw0qppa50289r5c9ku4k4
      Fullname: haxxor elite
      ...
```

## Cookies

Some services are required cookies for API requests. Follow next steps to use your cookies for YaSeeker:
1. Login into Yandex through your browser.
1. Install any extension to download all the Ya cookies in Netscape format aka cookies.txt  ([Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid), [Firefox](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)).
1. Save it to the directory of YaSeeker in file `cookies.txt`.
1. Run script and enjoy!
