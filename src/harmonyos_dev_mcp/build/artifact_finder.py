"""Build artifact discovery helpers."""

import json
import re
from pathlib import Path
from typing import Optional


def is_fresh_output(path: Optional[Path], not_before: Optional[float]) -> bool:
    if path is None or not path.exists():
        return False
    if not_before is None:
        return True
    try:
        return path.stat().st_mtime >= (not_before - 1.0)
    except OSError:
        return False


def resolve_sign_status(output_path: Optional[Path]) -> str:
    if output_path is None:
        return "unknown"
    lowered_name = output_path.name.lower()
    if lowered_name.endswith((".hap", ".hsp")):
        if "unsigned" in lowered_name:
            return "unsigned"
        if "signed" in lowered_name:
            return "signed"
    return "unknown"


def build_output_resolution_guidance(*, stale_logged_output: bool = False) -> str:
    guidance = [
        "Build completed, but the tool could not locate a fresh artifact for this run.",
    ]
    if stale_logged_output:
        guidance.append(
            "The path mentioned in hvigor output points to an existing artifact whose timestamp predates the current build."
        )
    else:
        guidance.append(
            "This usually means an incremental build reused cached outputs without updating timestamps, or the signed output path was not emitted in a way the tool could recognize."
        )
    guidance.append(
        "Try build_app with is_clean=true, or check whether the expected package already exists under the project's build outputs or hapsigner directory."
    )
    return " ".join(guidance)


class BuildArtifactFinder:
    """Resolve hvigor build artifacts from metadata, logs, or output folders."""

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path).resolve()

    def extract_output_path_from_logs(
        self,
        stdout: str,
        stderr: str,
        output_type: str,
        not_before: Optional[float] = None,
    ) -> Optional[Path]:
        extension = f".{output_type}"
        token_pattern = re.compile(rf"([A-Za-z]:[\\/][^\s'\"<>]+?{re.escape(extension)}|[^\s'\"<>]+?{re.escape(extension)})")

        for text in (stdout, stderr):
            for raw_match in token_pattern.findall(text or ""):
                candidate_text = raw_match.strip("\"'")
                candidate = Path(candidate_text)
                if candidate.is_absolute() and is_fresh_output(candidate, not_before):
                    return candidate

                relative_candidates = [
                    (self.project_path / candidate_text).resolve(),
                    (self.project_path / Path(candidate_text).name).resolve(),
                ]
                for relative_candidate in relative_candidates:
                    if is_fresh_output(relative_candidate, not_before):
                        return relative_candidate
        return None

    def find_output_from_metadata(
        self,
        output_type: str,
        product: str,
        module_name: Optional[str],
        not_before: Optional[float] = None,
    ) -> Optional[Path]:
        if output_type != "hap":
            return None

        module_root = self.project_path / (module_name or "entry")
        metadata_path = module_root / "build" / product / "intermediates" / "hap_metadata" / product / "output_metadata.json"
        if not metadata_path.exists():
            return None

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(metadata, list):
            return None

        for item in metadata:
            if not isinstance(item, dict):
                continue
            hap_name = item.get("hapName")
            if not hap_name:
                continue
            candidate = module_root / "build" / product / "outputs" / product / hap_name
            if is_fresh_output(candidate, not_before):
                return candidate
        return None

    def find_build_output(
        self,
        output_type: str,
        build_mode: str = "debug",
        product: str = "default",
        module_name: Optional[str] = None,
        not_before: Optional[float] = None,
    ) -> Optional[Path]:
        """Return the best build artifact for the requested output type."""
        output_dirs = [
            self.project_path / "build",
            self.project_path / "entry" / "build",
        ]
        if output_type == "hap":
            output_dirs.append(self.project_path / "hapsigner")
        if module_name:
            output_dirs.append(self.project_path / module_name / "build")

        matches: list[Path] = []
        extension = f".{output_type}"
        for output_dir in output_dirs:
            if not output_dir.exists():
                continue
            matches.extend(output_dir.rglob(f"*{extension}"))

        if output_type == "hap":
            matches = [path for path in matches if not self.is_test_artifact(path)]

        if not_before is not None:
            matches = [path for path in matches if is_fresh_output(path, not_before)]

        if not matches:
            return None

        if module_name:
            narrowed = [
                path
                for path in matches
                if module_name.lower() in path.name.lower()
                or module_name.lower() in str(path.parent).lower()
            ]
            if narrowed:
                matches = narrowed

        matches.sort(
            key=lambda path: self.score_output_path(path, output_type, build_mode, product, module_name),
            reverse=True,
        )
        return matches[0]

    @staticmethod
    def score_output_path(
        path: Path,
        output_type: str,
        build_mode: str,
        product: str,
        module_name: Optional[str],
    ) -> tuple[int, float]:
        lowered_name = path.name.lower()
        lowered_path = str(path).lower()
        score = 0

        if output_type in lowered_name:
            score += 20
        if "signed" in lowered_name and "unsigned" not in lowered_name:
            score += 30
        if build_mode and build_mode.lower() in lowered_path:
            score += 40
        if product and product.lower() in lowered_path:
            score += 40
        if module_name and module_name.lower() in lowered_path:
            score += 40
        if "outputs" in lowered_path:
            score += 10
        if output_type == "hap" and "unsigned" in lowered_name:
            score += 5
        if path.parent.name.lower() == product.lower():
            score += 10

        return score, path.stat().st_mtime

    @staticmethod
    def is_test_artifact(path: Path) -> bool:
        lowered_parts = {part.lower() for part in path.parts}
        lowered_name = path.name.lower()
        return "ohostest" in lowered_parts or "-ohostest-" in lowered_name
