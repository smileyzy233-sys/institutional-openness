"""Deprecated compatibility entry for the modular 2019 matching pipelines.

All matching logic now lives in ``match_y_x_*`` and ``match_y_x_cons_*``.
This wrapper requests the ``legacy_2019_v1`` comparison configuration and
never writes to ``result/regression_2019``.
"""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Any

from match_y_x_common import (
    load_matching_specs,
    load_sibling_script,
    project_directory,
    y_x_output_paths,
)
from match_y_x_cons_common import control_output_paths


def build_all(
    project_dir: Path | str | None = None,
    *,
    write_notebook_file: bool = False,
    force: bool = False,
    output_root: Path | str | None = None,
) -> dict[str, Any]:
    """Run or reuse the modular 2019 legacy-comparison outputs."""
    root = (
        Path(project_dir).resolve()
        if project_dir is not None
        else project_directory()
    )
    warnings.warn(
        "build_regression_2019.py is deprecated; use `python run_pipeline.py "
        "match-y-x` and `match-y-x-cons`.",
        DeprecationWarning,
        stacklevel=2,
    )
    if write_notebook_file:
        warnings.warn(
            "The compatibility wrapper no longer creates an audit notebook.",
            RuntimeWarning,
            stacklevel=2,
        )
    y_x_module = load_sibling_script("match_y_x_06_validate_export.py")
    controls_module = load_sibling_script(
        "match_y_x_cons_07_validate_export.py"
    )
    try:
        y_x_module.run(
            project_dir=root,
            years=[2019],
            output_root=output_root,
            force=force,
        )
    except FileExistsError:
        if force:
            raise
    try:
        controls_module.run(
            project_dir=root,
            years=[2019],
            control_spec="legacy_2019_v1",
            output_root=output_root,
            force=force,
        )
    except FileExistsError:
        if force:
            raise
    specs = load_matching_specs(root)
    y_x_paths = y_x_output_paths(root, specs, 2019, output_root)
    control_paths = control_output_paths(
        root, specs, "legacy_2019_v1", 2019, output_root
    )
    return {
        "deprecated_entry": "src/build_regression_2019.py",
        "year": 2019,
        "control_spec": "legacy_2019_v1",
        "y_x_manifest": str(y_x_paths["manifest"]),
        "controls_manifest": str(control_paths["manifest"]),
        "old_result_directory_written": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = build_all(output_root=args.output_root, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
