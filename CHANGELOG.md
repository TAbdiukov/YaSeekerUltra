# Changelog

## 0.3.3

- Added ignore patterns for Yandex Market CMS and advertising avatar-like assets.
- Fix typo
- Update CDN-cached images

## 0.3.0

- Fetch profile pictures safely and consistently
- Better cookie handling
- Add PyPI build metadata
- Rename project
- Update README
- Sunset pictures/

## 0.2.1

- High-level tests
- Fix Unicode issue in file put()
- Make relevant cookie loading status explicit with colourised output.
- Update README
- Update .gitignore

## 0.2.0

- Implement a case system utilizing timestamps for reports
- Fix stale `run.py` wrapper to delegate to the package CLI entrypoint.
- Make zero-lead results explicit in console, TXT, and CSV reports
- Save auxiliary TXT and CSV evidence reports inside each session folder
- Show the full per-session reports path in output
- Fix HTML metadata handling per encodings.
- Implement test-driven CI/CD.

## 0.1.0

- Fix Cookie handling
- Turn into a pip-installable package.

## 0.0.8

- Add per-input UTC-timestamped response sessions
- Save all attempted HTTP responses to session folders
- Embed response headers in saved HTML output where possible
- Save non-HTML responses as raw header-plus-body files
- Track progress by attempted URL hits per session

## 0.0.4

- Fixes to asyncio usage for Python 3.14 (Python 3.8 or higher), while maintaining backwards compatibility.
- Fix relative import in `__main__.py`
- Add URLs and request-method information to the final summary
- Add missing requirements to `requirements.txt`
- Fix flimsy packaging entrypoint
- Misc: Create changelog
- Misc: Update User-Agent
- Bump version

## 0.0.3

- ...
