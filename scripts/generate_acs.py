"""Generate upload-ready ACS files from the Partner templates.

The platform issues the AIC after the ACS is approved, so the generated file
does not include the ``aic`` field. Run this only after a public HTTPS hostname
is available for the corresponding Partner.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROLES = {
    "format": ("acs.format-partner.example.json", "REPLACE_WITH_FORMAT_HOST"),
    "logic": ("acs.logic-partner.example.json", "REPLACE_WITH_LOGIC_HOST"),
    "cross-stage": ("acs.cross-stage-partner.example.json", "REPLACE_WITH_CROSS_STAGE_HOST"),
}


def _load_template(competition_dir: Path, filename: str) -> dict:
    path = competition_dir / filename
    return json.loads(path.read_text(encoding="utf-8"))


def _render(template: dict, host: str, host_placeholder: str) -> dict:
    rendered = json.loads(json.dumps(template, ensure_ascii=False))
    rendered.pop("aic", None)
    rendered["lastModifiedTime"] = datetime.now(timezone.utc).isoformat()
    for endpoint in rendered.get("endPoints", []):
        if isinstance(endpoint, dict) and isinstance(endpoint.get("url"), str):
            endpoint["url"] = endpoint["url"].replace(
                host_placeholder, host.strip().rstrip("/")
            )
    certificate = rendered.get("certificate") or {}
    alt_names = certificate.get("altNames") or {}
    dns = alt_names.get("dns") or []
    alt_names["dns"] = [
        name.replace(host_placeholder, host.strip().rstrip("/")) for name in dns
    ]
    certificate["altNames"] = alt_names
    rendered["certificate"] = certificate
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Partner ACS files for upload")
    parser.add_argument("--host", required=True, help="public HTTPS hostname, without scheme")
    parser.add_argument(
        "--role",
        choices=sorted(ROLES),
        help="render only one role instead of all three",
    )
    parser.add_argument(
        "--competition-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "competition",
    )
    args = parser.parse_args()

    competition_dir: Path = args.competition_dir
    roles = [args.role] if args.role else list(ROLES)
    for role in roles:
        template_name, placeholder = ROLES[role]
        rendered = _render(_load_template(competition_dir, template_name), args.host, placeholder)
        out_name = f"acs.{role}-partner.json"
        out_path = competition_dir / out_name
        out_path.write_text(
            json.dumps(rendered, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(out_path)


if __name__ == "__main__":
    main()
