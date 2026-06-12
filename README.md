# YaSeekerUltra

<p align="center">
  <img src="./pictures/logo.jpg" />
</p>

YaSeekerUltra is an OSINT command line tool for checking public Yandex account
information by username, email address, or Yandex public ID.

It is a greatly updated package based on the original YaSeeker project. The old
`ya_seeker.py` command and `IDENTIFIER.txt` JSON output are no longer the main
interface. YaSeekerUltra is now intended to be installed as a Python package and
run with the `yaseeker` command, although it can still be run directly from a
source checkout.

Use this tool only for accounts you own or are authorised to investigate.

## What it can find

Depending on what Yandex services return, YaSeekerUltra may find:

- full name;
- profile photo or possible avatar URLs;
- gender;
- Yandex UID;
- Yandex public ID;
- linked social accounts;
- activity information, such as reviews, comments, subscribers, and subscriptions;
- account flags, such as verified, banned, deleted, restricted, or business status.

The tool currently checks Yandex services such as Music, Collections, Bugbounty,
Reviews, Q/Znatoki, O/Classified, Zen, Market, Messenger, and Kinopoisk.

Some services return useful information only when valid Yandex cookies are
provided. See [Cookies](#cookies).

## Requirements

- Python 3.8 or newer.
- `pip`.

Using a virtual environment is recommended so the package and its dependencies do
not affect other Python projects on your computer.

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Installation

### Install from PyPI

```bash
python -m pip install yaseeker
```

After installation, check that the command is available:

```bash
yaseeker --version
```

### Install directly from GitHub

```bash
python -m pip install git+https://github.com/soxoj/YaSeekerUltra.git
```

### Install from a local source checkout

```bash
git clone https://github.com/soxoj/YaSeekerUltra.git
cd YaSeekerUltra
python -m pip install .
```

For development, use editable mode:

```bash
python -m pip install -e .
```

### Run without installing the package

From the project directory:

```bash
python -m pip install -r requirements.txt
python -m yaseeker login
```

The compatibility wrapper also works:

```bash
python run.py login
```

## Usage

Basic usage:

```bash
yaseeker TARGET
```

Examples:

```bash
yaseeker login
yaseeker login@yandex.ru
yaseeker c48fhxw0qppa50289r5c9ku4k4
```

You can check several targets in one run:

```bash
yaseeker login another_login c48fhxw0qppa50289r5c9ku4k4
```

YaSeekerUltra automatically recognises input values:

| Input | How it is handled |
| --- | --- |
| `login` | Treated as a Yandex username. |
| `login@yandex.ru` | The email domain is removed and `login` is checked as a username. |
| `c48fhxw0qppa50289r5c9ku4k4` | A 26-character value is treated as a Yandex public ID. |

Do not pass the identifier type as a second positional argument. For example,
use this:

```bash
yaseeker c48fhxw0qppa50289r5c9ku4k4
```

not this:

```bash
yaseeker c48fhxw0qppa50289r5c9ku4k4 yandex_public_id
```

## Reading many targets

Read targets from a text file, one target per line:

```bash
yaseeker --target-list targets.txt
```

Read targets from standard input:

```bash
cat targets.txt | yaseeker --targets-from-stdin
```

## Reports and saved evidence

For every target, YaSeekerUltra creates a per-session folder under `reports/`.
The folder name contains a UTC timestamp and the target value, for example:

```text
reports/20260101T120000Z_login/
```

Each session folder may contain:

- attempted HTTP responses;
- raw non-HTML responses;
- saved HTML responses with request metadata;
- downloaded avatar images when possible;
- `auxiliary_report.txt`;
- `auxiliary_report.csv`.

The console output also shows a summary, including whether any leads were found.
A `No leads found` result means the checked services did not return useful
profile data for that target. It does not prove that the account does not exist.

Save an additional text report:

```bash
yaseeker login -oT report.txt
```

Save an additional CSV report:

```bash
yaseeker login -oC report.csv
```

Save both:

```bash
yaseeker login -oT report.txt -oC report.csv
```

Useful output options:

```bash
yaseeker login --no-progressbar
yaseeker login --no-color
yaseeker login --silent -oC report.csv
```

## Cookies

Some Yandex services require cookies before they return useful API responses.
YaSeekerUltra can read cookies in Netscape `cookies.txt` format.

1. Log in to Yandex in your browser.
2. Export your Yandex cookies in Netscape format. Browser extensions commonly
   call this format `cookies.txt`.
3. Save the file as `cookies.txt` in the directory where you run YaSeekerUltra.
4. Run the tool normally.

You can also pass a custom cookie file path:

```bash
yaseeker login --cookie-jar-file /path/to/cookies.txt
```

When cookies are loaded, YaSeekerUltra prints whether any of them match the
Yandex domains queried by the tool. If you see a message saying that no cookies
match queried domains, check that you exported the right browser profile and
that the file contains Yandex cookies.

## Proxy

Requests can be sent through a proxy:

```bash
yaseeker login --proxy socks5://127.0.0.1:1080
```

## Common problems

### `There are no targets to check!`

Pass at least one target, provide `--target-list`, or use
`--targets-from-stdin`.

### `Cookies not found`

The tool can still run, but some services may not return useful data. Add a
`cookies.txt` file or pass `--cookie-jar-file`.

### `Captcha detected`

Yandex returned a captcha page instead of the expected service response. Try
again later, use valid cookies, or reduce repeated requests.

### The command `yaseeker` is not found

Check that the package was installed in the same Python environment that you are
using in your terminal:

```bash
python -m pip show yaseeker
python -m yaseeker --version
```

## Development

Run tests:

```bash
make test
```

Run lint checks:

```bash
make lint
```

Format code:

```bash
make format
```

The CI workflow currently runs pytest on Python 3.11, 3.12, 3.13, and 3.14.

## SOWEL classification

This tool uses the following OSINT techniques:

- [SOTL-1.4. Analyze Internal Identifiers](https://sowel.soxoj.com/internal-identifiers)
- [SOTL-2.2. Search For Accounts On Other Platforms](https://sowel.soxoj.com/other-platform-accounts)
- [SOTL-6.1. Check Logins Reuse To Find Another Account](https://sowel.soxoj.com/logins-reuse)
- [SOTL-6.2. Check Nicknames Reuse To Find Another Account](https://sowel.soxoj.com/nicknames-reuse)
