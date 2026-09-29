"""Validate the HACS metadata of this repository.

`hacs.json` is not just documentation: HACS parses it with the schema below and
refuses to install a repository that violates it. The 2.1.0 release shipped a
`hacs.json` inherited from the old `master` line that contained

    "zip_release": true

without a `filename`, which HACS rejects ("zip_release is True, but filename is
not set") and which made installation fail with

    Failed to perform the action update/install. 'NoneType' object has no
    attribute 'endswith'

because the download step then calls `filename.endswith(...)`.

The schemas are copies of HACS's own
(`custom_components/hacs/utils/validate.py` -> `HACS_MANIFEST_JSON_SCHEMA`,
`INTEGRATION_MANIFEST_JSON_SCHEMA`, and
`custom_components/hacs/validate/hacsjson.py`). Keep them in sync when HACS
changes them.

Run:  python tests/verify_hacs_manifest.py
"""

from __future__ import annotations

import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# The harness dependency lives in the (gitignored) vendor folder, like in
# tests/verify_config_flow.py.
sys.path.insert(0, str(REPO / "tests" / "vendor"))

try:
    import voluptuous as vol
except ImportError:
    sys.exit(
        "voluptuous is required: python -m pip install --target tests/vendor voluptuous"
    )

HACS_JSON = REPO / "hacs.json"
MANIFEST_JSON = REPO / "custom_components" / "crowipmodule" / "manifest.json"
INFO_FILES = ("readme.md", "readme", "info.md", "info")

# --- copied from HACS: custom_components/hacs/utils/validate.py ---------------
# Allowed keys. `extra=vol.PREVENT_EXTRA` means an unknown key is an ERROR, so
# inherited keys from other ecosystems (iot_class, domains, ...) must not linger.
HACS_MANIFEST_JSON_SCHEMA = vol.Schema(
    {
        vol.Optional("content_in_root"): bool,
        vol.Optional("country"): vol.Any(list, str),
        vol.Optional("filename"): str,
        vol.Optional("hacs"): str,
        vol.Optional("hide_default_branch"): bool,
        vol.Optional("homeassistant"): str,
        vol.Optional("persistent_directory"): str,
        vol.Optional("render_readme"): bool,
        vol.Optional("zip_release"): bool,
        vol.Required("name"): str,
    },
    extra=vol.PREVENT_EXTRA,
)

INTEGRATION_MANIFEST_JSON_SCHEMA = vol.Schema(
    {
        vol.Required("codeowners"): list,
        vol.Required("documentation"): str,
        vol.Required("domain"): str,
        vol.Required("issue_tracker"): str,
        vol.Required("name"): str,
        vol.Required("version"): str,
    },
    extra=vol.ALLOW_EXTRA,
)
# -----------------------------------------------------------------------------

FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"[PASS] {message}")
    else:
        print(f"[FAIL] {message}")
        FAILURES.append(message)


def main() -> int:
    if not HACS_JSON.is_file():
        sys.exit("hacs.json is missing - HACS would report the repository as invalid")

    raw = json.loads(HACS_JSON.read_text(encoding="utf-8"))
    print(f"hacs.json = {json.dumps(raw, indent=2)}\n")

    try:
        HACS_MANIFEST_JSON_SCHEMA(raw)
        check(True, "hacs.json matches HACS_MANIFEST_JSON_SCHEMA (no unknown keys)")
    except vol.Invalid as err:
        check(False, f"hacs.json violates the HACS schema: {err}")

    # The rule that broke 2.1.0 (validate/hacsjson.py, INTEGRATION category).
    check(
        not (raw.get("zip_release") and not raw.get("filename")),
        "zip_release is not set without a filename",
    )
    check(
        not raw.get("zip_release"),
        "zip_release is not used at all (this integration ships its source, "
        "not a release asset)",
    )
    check(raw.get("name") == "Crow/AAP Alarm IP Module", "hacs.json name matches the repository")
    check("homeassistant" in raw, "hacs.json pins a minimum Home Assistant version")

    # A repository must have a readme or an info.md (validate/information.py).
    files = [p.name.lower() for p in REPO.iterdir()]
    check(
        any(name in files for name in INFO_FILES),
        "the repository has a readme/info file",
    )
    check((REPO / "LICENSE").is_file(), "the repository has a LICENSE (validate/license.py)")

    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    try:
        INTEGRATION_MANIFEST_JSON_SCHEMA(manifest)
        check(True, "manifest.json matches INTEGRATION_MANIFEST_JSON_SCHEMA")
    except vol.Invalid as err:
        check(False, f"manifest.json violates the HACS schema: {err}")

    check(manifest.get("domain") == "crowipmodule", "manifest domain is crowipmodule")
    check(
        (REPO / "custom_components" / manifest["domain"]).is_dir(),
        f"custom_components/{manifest.get('domain')}/ exists",
    )

    # HACS compares the release tag against the manifest version.
    tag = manifest["version"]
    check(
        raw.get("hacs", tag) == tag,
        f"manifest version {tag!r} is what HACS will compare against the tag",
    )

    print("\n" + "=" * 40)
    if FAILURES:
        print(f"{len(FAILURES)} of {CHECKS} checks FAILED")
        return 1
    print(f"ALL {CHECKS} CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
