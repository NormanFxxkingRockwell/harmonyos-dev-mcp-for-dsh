import json
import os
from pathlib import Path

from harmonyos_dev_mcp.build.artifact_finder import (
    BuildArtifactFinder,
    build_output_resolution_guidance,
    is_fresh_output,
    resolve_sign_status,
)


def _write_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_find_output_from_metadata_returns_fresh_hap(tmp_path):
    project = tmp_path / "MyApplication"
    artifact = project / "entry" / "build" / "default" / "outputs" / "default" / "entry-default-signed.hap"
    metadata = project / "entry" / "build" / "default" / "intermediates" / "hap_metadata" / "default" / "output_metadata.json"
    _write_file(artifact, "signed")
    _write_file(metadata, json.dumps([{"hapName": artifact.name}]))

    finder = BuildArtifactFinder(project)

    assert finder.find_output_from_metadata("hap", "default", None, not_before=0) == artifact
    assert resolve_sign_status(artifact) == "signed"


def test_extract_output_path_from_logs_handles_relative_paths(tmp_path):
    project = tmp_path / "MyApplication"
    artifact = project / "entry" / "build" / "default" / "outputs" / "default" / "entry-default-unsigned.hap"
    _write_file(artifact, "unsigned")

    finder = BuildArtifactFinder(project)

    result = finder.extract_output_path_from_logs(
        f"artifact: {artifact.relative_to(project)}",
        "",
        "hap",
        not_before=0,
    )

    assert result == artifact
    assert resolve_sign_status(result) == "unsigned"


def test_find_build_output_scores_and_filters_test_hap(tmp_path):
    project = tmp_path / "MyApplication"
    older = project / "build" / "outputs" / "old-release.hap"
    app_artifact = project / "entry" / "build" / "default" / "outputs" / "default" / "entry-default-unsigned.hap"
    test_artifact = project / "entry" / "build" / "default" / "outputs" / "ohosTest" / "entry-ohosTest-signed.hap"
    _write_file(older, "old")
    _write_file(app_artifact, "app")
    _write_file(test_artifact, "test")
    os.utime(older, (300, 300))
    os.utime(app_artifact, (200, 200))
    os.utime(test_artifact, (400, 400))

    finder = BuildArtifactFinder(project)

    assert finder.find_build_output("hap", build_mode="debug", product="default") == app_artifact
    assert not finder.is_test_artifact(app_artifact)
    assert finder.is_test_artifact(test_artifact)


def test_freshness_and_resolution_guidance(tmp_path):
    artifact = tmp_path / "entry-default-signed.hap"
    _write_file(artifact, "signed")
    os.utime(artifact, (100, 100))

    assert is_fresh_output(artifact, 100)
    assert not is_fresh_output(artifact, 500)
    assert "could not locate a fresh artifact" in build_output_resolution_guidance()
    assert "timestamp predates" in build_output_resolution_guidance(stale_logged_output=True)
