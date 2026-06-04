import json
import zipfile
from pathlib import Path

from harmonyos_dev_mcp.build.packaging_hnp import HnpPackager
from harmonyos_dev_mcp.build.packaging_hsp import HspPackager
from harmonyos_dev_mcp.build.signing import SigningHelper


def _write_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_hsp(path: Path, module_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pack_info = {
        "summary": {
            "modules": [
                {
                    "distro": {"moduleName": module_name},
                }
            ]
        },
        "packages": [{"name": module_name}],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("pack.info", json.dumps(pack_info))


def test_signing_helper_resolves_repack_signing_config(tmp_path):
    project = tmp_path / "MyApplication"
    profile = project / "build-profile.json5"
    _write_file(
        profile,
        """
        {
          "app": {
            "signingConfigs": [
              {
                "name": "default",
                "material": {
                  "certpath": "./sign/application.pem",
                  "keyAlias": "debug",
                  "keyPassword": "123456",
                  "profile": "./sign/default.p7b",
                  "storeFile": "./sign/application.p12",
                  "storePassword": "123456"
                }
              }
            ],
            "products": [
              {
                "name": "default",
                "signingConfig": "default",
                "compatibleSdkVersion": "5.0.0(12)"
              }
            ]
          }
        }
        """,
    )
    _write_file(project / "sign" / "application.pem", "cert")
    _write_file(project / "sign" / "default.p7b", "profile")
    _write_file(project / "sign" / "application.p12", "store")
    helper = SigningHelper(
        project,
        project / "sdk",
        None,
        build_env=lambda: {},
        which=lambda name: None,
    )

    result = helper.resolve_repack_signing_config([profile], "default", "HNP")

    assert result["success"] is True
    assert result["compatible_version"] == "12"
    assert result["keystore_file"] == project / "sign" / "application.p12"


def test_hnp_packager_finds_source_root_and_ignores_build_outputs(tmp_path):
    project = tmp_path / "MyApplication"
    module_root = project / "entry"
    _write_file(module_root / "build" / "tmp" / "ignored.hnp", "ignored")
    _write_file(module_root / "src" / "main" / "hnp" / "arm64-v8a" / "xrdp.hnp", "hnp")
    helper = SigningHelper(project, project / "sdk", None, build_env=lambda: {})
    packager = HnpPackager(project, helper)

    assert packager.find_source_root(module_root) == module_root / "src" / "main" / "hnp"


def test_hsp_packager_merges_pack_info(tmp_path):
    project = tmp_path / "MyApplication"
    module_root = project / "entry"
    outputs_root = module_root / "build" / "default" / "outputs" / "default"
    base_pack_info = outputs_root / "pack.info"
    hsp_path = project / "library" / "build" / "default" / "outputs" / "default" / "library-default-signed.hsp"
    _write_file(
        base_pack_info,
        json.dumps(
            {
                "summary": {"modules": [{"distro": {"moduleName": "entry"}}]},
                "packages": [{"name": "entry"}],
            }
        ),
    )
    _write_hsp(hsp_path, "library")

    result = HspPackager.merge_pack_info(base_pack_info, [hsp_path], outputs_root, module_root)

    assert result["success"] is True
    merged = json.loads(result["pack_info"].read_text(encoding="utf-8"))
    module_names = [module["distro"]["moduleName"] for module in merged["summary"]["modules"]]
    package_names = [package["name"] for package in merged["packages"]]
    assert module_names == ["entry", "library"]
    assert package_names == ["entry", "library"]
