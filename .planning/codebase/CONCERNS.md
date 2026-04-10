# Concerns

**Analysis Date:** 2026-04-10

## Highest Priority

- `data.py:140-149`, `data.py:226-227`, `data.py:252-255`, and `data.py:292-293` use `pickle.load` and `pickle.dump` for both caches without any schema, version, or integrity check. A corrupted or tampered cache can crash the run, and unpickling is unsafe for untrusted inputs.
- `data.py:235-255` returns cached TECH values immediately without checking `seasons` or `season_weights`. If either config changes, `tech_cache.pkl` can silently serve stale estimates until the file is deleted.
- `data.py:194-223` treats failed player-season fetches as skips and still persists the partial cache. The pipeline keeps going without a final missing-data summary, so tau and projections can be biased by silent gaps.
- `validate.py:104-106` returns an empty dict when no players match, and `main.py:165-180` ignores the returned result. A broken validation CSV, schema drift, or name mismatch can therefore look like a normal successful run.

## Modeling Risks

- `model.py:45-96` reweights every season using only PTS trend. That keeps the code simple, but it can misread players whose value changes in rebounds, assists, steals, or blocks without a matching scoring trend.
- `model.py:348-365` requires at least four weighted weekly observations before computing player-specific tau. Short-sample players fall back to league median variance, which flattens the variance penalty for rookies, call-ups, and injury returnees.
- `model.py:393-398` truncates the scoring pool to the top `num_teams * roster_size` players by prior-season `MIN` before any category scoring happens. Players outside that pre-filter cannot rise into the rankings even if the projection model thinks they should.

## Maintenance Risks

- `requirements.txt:1-5` uses loose minimum version pins and no lockfile. `nba_api` in particular is likely to drift, which raises the chance of endpoint, column, or response-shape breakage.
- `main.py:28-33` and `config.py:55-67` have to stay in sync manually for season files, game-log seasons, and cache expectations. A mismatch produces hard-to-notice projection drift rather than an obvious configuration error.

## Testing Gaps

- `tests/test_data.py:12-44`, `tests/test_model.py:8-97`, and `tests/test_validate.py:10-60` cover normalization and a few happy-path calculations, but they do not exercise cache invalidation, partial fetch failures, validation failure handling, or stale TECH cache reuse.
