# Openverse API Reference

Openverse API base URL: `https://api.openverse.org/v1`

The OpenAPI schema is available at `https://api.openverse.org/v1/schema/?format=json`.

## OAuth

This skill requires OAuth credentials and does not use anonymous requests.

Token endpoint:

```text
POST /auth_tokens/token/
Content-Type: application/x-www-form-urlencoded
```

Form fields:

- `grant_type=client_credentials`
- `client_id=<OPENVERSE_CLIENT_ID>`
- `client_secret=<OPENVERSE_CLIENT_SECRET>`

Use the returned access token in subsequent API requests:

```text
Authorization: Bearer <access_token>
```

Openverse registration exists at `/auth_tokens/register/`, but this skill intentionally does not include a registration command. Ask the user to configure `OPENVERSE_CLIENT_ID` and `OPENVERSE_CLIENT_SECRET`.

## Endpoints

Search:

- `GET /images/`
- `GET /audio/`

Details:

- `GET /images/{identifier}/`
- `GET /audio/{identifier}/`

Related:

- `GET /images/{identifier}/related/`
- `GET /audio/{identifier}/related/`

Stats/source discovery:

- `GET /images/stats/`
- `GET /audio/stats/`

## Search Parameters

Common image/audio parameters:

- `q`: query string, max 200 characters
- `page`
- `page_size`
- `source`: comma-separated source names from the relevant stats endpoint
- `excluded_source`
- `tags`: tag-only fuzzy search; cannot be used with `q`
- `title`: title-only fuzzy search; cannot be used with `q`
- `creator`: creator-only fuzzy search; ignored when `q` is present
- `license`: comma-separated licenses, such as `cc0`, `by`, `by-sa`, `by-nc`, `pdm`
- `license_type`: `all`, `all-cc`, `commercial`, or `modification`
- `filter_dead`
- `extension`
- `mature`

Image-specific parameters:

- `category`: `digitized_artwork`, `illustration`, `photograph`
- `aspect_ratio`: `square`, `tall`, `wide`
- `size`: `large`, `medium`, `small`

Audio-specific parameters:

- `category`: `audiobook`, `music`, `news`, `podcast`, `pronunciation`, `sound_effect`
- `length`: `long`, `medium`, `short`, `shortest`
- `peaks`: include waveform peaks

Avoid unstable parameters unless the user explicitly needs experimental behavior.

## Response Fields

Paginated responses include:

- `result_count`
- `page_count`
- `page_size`
- `page`
- `results`
- `warnings`

Useful image fields:

- `id`
- `title`
- `creator`
- `provider`
- `source`
- `url`
- `thumbnail`
- `foreign_landing_url`
- `license`
- `license_version`
- `license_url`
- `attribution`
- `height`
- `width`
- `detail_url`
- `related_url`

Useful audio fields:

- `id`
- `title`
- `creator`
- `provider`
- `source`
- `url`
- `thumbnail`
- `foreign_landing_url`
- `license`
- `license_version`
- `license_url`
- `attribution`
- `duration`: milliseconds
- `filetype`
- `alt_files`
- `waveform`
- `detail_url`
- `related_url`
