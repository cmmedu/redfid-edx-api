# Suppressed / ignored test warnings

This documents the 29 warnings emitted by the `pytest` run for
`redfid_edx_api` (via the `act`-driven CI workflow). **None originate
from `redfid_edx_api`'s own code** — all 29 come from edx-platform
internals, a bundled fork (django-wiki), or third-party/edX apps that get
imported as a side effect of the LMS test settings loading. They are listed
here for reference, grouped by source, with the reason each is safe to
ignore.

## edx-platform core / bundled forks

| Source | Warning | Why it's safe to ignore |
|---|---|---|
| `edx-platform/common/lib/safe_lxml/safe_lxml/etree.py:20` | `defusedxml.lxml` no longer supported | edX's own compat shim; fix belongs in edx-platform, not this plugin |
| `edx-platform/src/django-wiki/django_notify/urls.py:11` | Invalid `\d` escape sequence (should be a raw string) | Bundled django-wiki fork inside edx-platform, unrelated to this plugin |
| `edx-platform/src/django-wiki/django_notify/urls.py:12` | Invalid `\d` escape sequence (should be a raw string) | Same as above |

## Third-party / transitive dependencies

| Source | Warning | Why it's safe to ignore |
|---|---|---|
| `past/builtins/misc.py:45` (python-future) | `imp` module deprecated | Third-party package pulled in transitively; not our import |
| `contracts/library/miscellaneous_aliases.py:19` (PyContracts) | `collections.Container` should be `collections.abc.Container` | Third-party package (PyContracts) |
| `contracts/library/miscellaneous_aliases.py:21` | `collections.Iterable` → `collections.abc.Iterable` | Same package |
| `contracts/library/miscellaneous_aliases.py:23` | `collections.Hashable` → `collections.abc.Hashable` | Same package |
| `contracts/library/miscellaneous_aliases.py:27` | `collections.Iterator` → `collections.abc.Iterator` | Same package |
| `contracts/library/miscellaneous_aliases.py:28` | `collections.Sequence` → `collections.abc.Sequence` | Same package |
| `contracts/library/miscellaneous_aliases.py:29` | `collections.Callable` → `collections.abc.Callable` | Same package |
| `contracts/library/miscellaneous_aliases.py:30` | `collections.Sized` → `collections.abc.Sized` | Same package |
| `contracts/library/miscellaneous_aliases.py:31` | `collections.Set` → `collections.abc.Set` | Same package |
| `contracts/library/miscellaneous_aliases.py:32` | `collections.MutableSequence` → `collections.abc.MutableSequence` | Same package |
| `contracts/library/miscellaneous_aliases.py:33` | `collections.MutableSet` → `collections.abc.MutableSet` | Same package |
| `contracts/library/miscellaneous_aliases.py:34` | `collections.Mapping` → `collections.abc.Mapping` | Same package |
| `contracts/library/miscellaneous_aliases.py:35` | `collections.MutableMapping` → `collections.abc.MutableMapping` | Same package |
| `newrelic/console.py:84` | `inspect.formatargspec` deprecated | New Relic APM agent installed in the LMS image, unrelated to this plugin |
| `sorl/thumbnail/conf/__init__.py:16` | `DEFAULT_CONTENT_TYPE` setting deprecated (Django 3.0) | `sorl-thumbnail` package (edx-platform dependency, thumbnails) |
| `sorl/thumbnail/conf/__init__.py:16` | `FILE_CHARSET` setting deprecated (Django 3.1) | Same package |

## `enterprise` app (edX) — `DeprecatedEdxPlatformImportWarning`

Fired by edX's `enterprise` app simply being installed/loaded during test
bootstrap; the deprecated old-style imports (`student`, `third_party_auth`,
`track` instead of `common.djangoapps.*`) are in `enterprise`'s own code,
not ours.

| Source | Deprecated import |
|---|---|
| `enterprise/utils.py:63` | `student` instead of `common.djangoapps.student` |
| `enterprise/utils.py:63` | `student.api` instead of `common.djangoapps.student.api` |
| `enterprise/utils.py:74` | `third_party_auth` instead of `common.djangoapps.third_party_auth` |
| `enterprise/utils.py:74` | `third_party_auth.provider` instead of `common.djangoapps.third_party_auth.provider` |
| `enterprise/utils.py:81` | `track` instead of `common.djangoapps.track` |
| `enterprise/admin/forms.py:35` | `third_party_auth.models` instead of `common.djangoapps.third_party_auth.models` |
| `enterprise/signals.py:40` | `student.models` instead of `common.djangoapps.student.models` |

## XBlocks — only during `test_get_xblock_user_data_freetextresponse`

These three only appear when
`redfid_edx_api/tests.py::TestRedfidEdxApi::test_get_xblock_user_data_freetextresponse`
runs, because that test builds course content using the `poll` and
`staff_graded` XBlocks (alongside `freetextresponse`, which this endpoint
targets). The deprecated imports are inside those XBlock packages' own
code, not in `redfid_edx_api`.

| Source | Deprecated import |
|---|---|
| `poll/poll.py:56` | `static_replace` instead of `common.djangoapps.static_replace` |
| `staff_graded/staff_graded.py:27` | `course_modes` instead of `common.djangoapps.course_modes` |
| `staff_graded/staff_graded.py:27` | `course_modes.models` instead of `common.djangoapps.course_modes.models` |

## Summary

- Total warnings: 29
- Originating in `redfid_edx_api/`: 0
- All 29 are noise from the edx-platform test environment (core platform,
  bundled forks, and other installed apps/XBlocks) and are not actionable
  from this repository.

`setup.cfg`'s `[tool:pytest]` `filterwarnings` now adds explicit `ignore`
entries (by message regex) covering all 29 warnings above, on top of the
existing `default` plus the two pre-existing targeted ignores (rate-limit
warning, `FieldDataDeprecationWarning`). The warnings summary should now
only surface warnings actually caused by `redfid_edx_api`'s own code.
