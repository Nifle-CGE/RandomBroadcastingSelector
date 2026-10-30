# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

RandomBroadcastingSelector (web-rbs.com): a Flask site where every 24h one random registered user is picked to post a single message that all visitors see, vote on and can report. Logs and comments in the code are in French.

## Commands

- Dev run: `docker compose up --build` (reads `.env.dev`, serves on port 80 → 8000, runs `python app.py`). Or locally `python app.py` with the env vars below exported.
- Lint (also runs inside both Dockerfiles, so a lint error fails the image build): `flake8 --ignore=E501 .`
- There are no tests.
- Translations (full commands are in `babel.cfg`):
  - `pybabel extract -F babel.cfg -k lazy_gettext -o messages.pot --no-wrap --ignore-dirs 'tests' --ignore-dirs '.*' --ignore-dirs '_*' .`
  - `pybabel update -i messages.pot -d translations --no-wrap`
  - `pybabel compile -d translations` (the compiled `.mo` is committed)

## Configuration

All config comes from env vars, read in `_stuffimporter.StuffImporter.get_config()` plus `RBS_DEBUG` (required, `0`/`1`) and `SECRET_KEY` in `app.py`. The app talks to Azure Cosmos DB and DeepL **at import time**, so it cannot start without valid `DB_URL`/`DB_KEY`/`DEEPL_AUTH_KEY`. `RBS_DEBUG=1` disables the broadcaster rotation and prints mails instead of sending them.

## Architecture

- `app.py` holds everything: setup, routes, WTForms forms, custom validators, admin panel. `user.py` is the Flask-Login `User` model with `uimport`/`uexport` to Cosmos. `_stuffimporter.py` is config plus small helpers (random broadcaster pick, duration formatting).
- **Global state lives in one Cosmos document**, `stats.json` in container "Web RBS Stats" (shape: `samples/sample_stats.json`). It is loaded once into the module-global `stats` dict at startup, mutated in memory by requests, and written back whole with `stuffimporter.set_stats(stats)`. It holds the live broadcast, its votes/reports/translations, and the role lists (`broadcaster`, `futur_broadcasters`, `preselecteds`, `admin`, `moderators`, `ban_appealers`). This only works with a single gunicorn worker; any mutation must be followed by `set_stats` or it is lost on restart.
- Other containers: "Web RBS Users" (id = `<provider prefix>_<provider id>`, e.g. `ggl_…`, `gthb_…`) and "Web RBS Posts" (archived broadcasts, id = incrementing string number). New documents are built from the templates in `samples/sample_post.json` and `samples/sample_user_part.json`.
- **Broadcast lifecycle** is driven by `verify_broadcast()`, a `before_request` hook: once 24h have passed (`brod_change_threshold`) it archives the live post to the Posts container (or marks the broadcaster as "missed" → `preselecteds`, who can opt in again via `/reselect/`), picks the next broadcaster (`futur_broadcasters` queue first, else random), and emails them. There is no background job; the first request after the deadline does this work.
- Roles are checked with `@role_required("<stats roles key>")` against `stats["roles"]`, not stored on the user document.
- Reports from users can auto-ban the author (condition in `index()`); bans live in the user doc's `ban` field, and banned users go through `/ban-appeal/` with a one-time code stored in `stats["roles"]["ban_appealers"]`.
- Translations of the live post are fetched lazily per viewer language by `ensure_trad()` and cached in `stats["broadcast"]["trads"]`; `TARGET_CODES` maps 2-letter codes to valid DeepL target codes.
- Security headers via Flask-Talisman with a strict CSP: inline `<script>`/`<style>` and external resources need `nonce="{{ csp_nonce() }}"` (see `templates/base.html`). HTTPS is terminated by Cloudflare (`force_https=False`).
- OAuth (Authlib): Google, Twitter, GitHub, Discord. Each provider is registered inside its login route; callbacks all end in `login_or_create_user()`. Twitch/Facebook are commented out.

## Commits

When a commit contains code written by Claude, say so in the commit message body (e.g. "Code written by Claude Code.") in addition to the `Co-Authored-By` trailer. Keep the user's own changes in separate commits without that line.

## Deployment

Pushing to `master` triggers `.github/workflows/main.yml`: builds the `web` (`Dockerfile.prod`, gunicorn) and `nginx` images, pushes them to ghcr.io, then SSHes to the Oracle server and runs `docker-compose.prod.yml`. Secrets are written into `.env` / `.env.prod` from GitHub secrets in the workflow, so a new env var must be added there in both jobs.
