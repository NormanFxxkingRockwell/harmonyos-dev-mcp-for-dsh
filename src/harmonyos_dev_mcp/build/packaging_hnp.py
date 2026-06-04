"""HNP packaging helpers."""

import shutil
import zipfile
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .signing import SigningHelper, merge_outputs


def hap_contains_hnp(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.startswith("hnp/") and name.endswith(".hnp") for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class HnpPackager:
    """Repack and sign HAPs with HNP payloads."""

    def __init__(self, project_path: Path, signing_helper: SigningHelper):
        self.project_path = Path(project_path).resolve()
        self.signing_helper = signing_helper

    @staticmethod
    def contains_hnp_package(path: Path) -> bool:
        if not path.exists():
            return False
        ignored_parts = {".git", ".hvigor", "build", "node_modules", "oh_modules"}
        for hnp in path.rglob("*.hnp"):
            if ignored_parts & {part.lower() for part in hnp.parts}:
                continue
            return True
        return False

    @staticmethod
    def hnp_root_for_package(package_path: Path) -> Path:
        abi_names = {"arm64-v8a", "armeabi-v7a", "x86_64", "x86"}
        if package_path.parent.name in abi_names:
            return package_path.parent.parent
        return package_path.parent

    def find_source_root(self, module_root: Path) -> Optional[Path]:
        candidates = [
            module_root / "hnp",
            module_root / "src" / "main" / "hnp",
            self.project_path / "hnp",
        ]
        for candidate in candidates:
            if self.contains_hnp_package(candidate):
                return candidate.resolve()

        ignored_parts = {".git", ".hvigor", "build", "node_modules", "oh_modules"}
        search_roots = [module_root, self.project_path]
        for root in search_roots:
            if not root.exists():
                continue
            for package_path in root.rglob("*.hnp"):
                if ignored_parts & {part.lower() for part in package_path.parts}:
                    continue
                return self.hnp_root_for_package(package_path).resolve()
        return None

    @staticmethod
    def stage_source(source_root: Path, outputs_root: Path, module_root: Path) -> Path:
        staging_root = (outputs_root / "native").resolve()
        if not path_inside(staging_root, module_root):
            raise ValueError(f"refusing to stage HNP packages outside module root: {staging_root}")

        if staging_root.exists():
            shutil.rmtree(staging_root)
        staging_root.mkdir(parents=True, exist_ok=True)
        for child in source_root.iterdir():
            destination = staging_root / child.name
            if child.is_dir():
                shutil.copytree(child, destination)
            else:
                shutil.copy2(child, destination)
        return staging_root

    def repack_and_sign(
        self,
        module_root: Path,
        hnp_source_root: Path,
        product: str,
        signing: dict[str, Any],
    ) -> dict[str, Any]:
        app_packing_tool = self.signing_helper.find_toolchain_jar("app_packing_tool.jar")
        hap_sign_tool = self.signing_helper.find_toolchain_jar("hap-sign-tool.jar")
        if app_packing_tool is None or hap_sign_tool is None:
            missing = []
            if app_packing_tool is None:
                missing.append("app_packing_tool.jar")
            if hap_sign_tool is None:
                missing.append("hap-sign-tool.jar")
            return {
                "success": False,
                "error_code": "HNP_TOOLCHAIN_NOT_FOUND",
                "stdout": "",
                "stderr": "required SDK toolchain jars were not found: " + ", ".join(missing),
                "output_path": None,
            }

        build_root = module_root / "build" / product
        intermediates = build_root / "intermediates"
        outputs = build_root / "outputs" / product
        packaging_inputs = {
            "json": intermediates / "package" / product / "module.json",
            "resources": intermediates / "res" / product / "resources",
            "ets": intermediates / "loader_out" / product / "ets",
            "index": intermediates / "res" / product / "resources.index",
            "pack_info": outputs / "pack.info",
            "pkg_context": intermediates / "loader" / product / "pkgContextInfo.json",
        }
        missing_inputs = [str(path) for path in packaging_inputs.values() if not path.exists()]
        if missing_inputs:
            return {
                "success": False,
                "error_code": "HNP_PACKAGING_INPUT_MISSING",
                "stdout": "",
                "stderr": "HNP packaging inputs were not found: " + ", ".join(missing_inputs),
                "output_path": None,
            }

        outputs.mkdir(parents=True, exist_ok=True)
        hnp_staging_root = self.stage_source(hnp_source_root, outputs, module_root)
        module = module_root.name
        unsigned_hnp = outputs / f"{module}-{product}-unsigned-hnp.hap"
        signed_hnp = outputs / f"{module}-{product}-signed-hnp.hap"
        lib_path = intermediates / "libs" / product
        java = self.signing_helper.java_command()

        pack_cmd = [
            java,
            "-jar",
            str(app_packing_tool),
            "--mode",
            "hap",
            "--json-path",
            str(packaging_inputs["json"]),
            "--resources-path",
            str(packaging_inputs["resources"]),
            "--ets-path",
            str(packaging_inputs["ets"]),
            "--out-path",
            str(unsigned_hnp),
            "--hnp-path",
            str(hnp_staging_root),
            "--index-path",
            str(packaging_inputs["index"]),
            "--pack-info-path",
            str(packaging_inputs["pack_info"]),
            "--pkg-context-path",
            str(packaging_inputs["pkg_context"]),
            "--force",
            "true",
        ]
        if lib_path.exists():
            pack_cmd.extend(["--lib-path", str(lib_path)])

        logger.info(f"repacking HAP with HNP packages from {hnp_source_root}")
        pack_result = self.signing_helper.run_packaging_command(pack_cmd, "HNP_REPACK")
        if not pack_result["success"] or not unsigned_hnp.exists():
            return {
                **pack_result,
                "output_path": None,
                "error_code": pack_result.get("error_code") or "HNP_REPACK_FAILED",
            }

        logger.info(f"signing HAP with HNP packages: {signed_hnp}")
        sign_failures: list[dict[str, Any]] = []
        successful_sign_result: Optional[dict[str, Any]] = None
        for key_password, keystore_password in self.signing_helper.password_candidates(signing):
            signed_hnp.unlink(missing_ok=True)
            sign_cmd = self.signing_helper.build_hap_sign_command(
                java,
                hap_sign_tool,
                unsigned_hnp,
                signed_hnp,
                signing,
                key_password,
                keystore_password,
            )
            sign_result = self.signing_helper.run_packaging_command(sign_cmd, "HNP_SIGN")
            if sign_result["success"] and signed_hnp.exists():
                successful_sign_result = sign_result
                break
            sign_failures.append(sign_result)

        if successful_sign_result is None:
            combined_stdout = merge_outputs(
                pack_result.get("stdout"),
                *(failure.get("stdout") for failure in sign_failures),
            )
            combined_stderr = merge_outputs(
                pack_result.get("stderr"),
                *(failure.get("stderr") for failure in sign_failures),
            )
            last_failure = sign_failures[-1] if sign_failures else {}
            return {
                "success": False,
                "error_code": last_failure.get("error_code") or "HNP_SIGN_FAILED",
                "stdout": combined_stdout,
                "stderr": combined_stderr,
                "output_path": None,
            }

        combined_stdout = merge_outputs(pack_result.get("stdout"), successful_sign_result.get("stdout"))
        combined_stderr = merge_outputs(pack_result.get("stderr"), successful_sign_result.get("stderr"))
        if not hap_contains_hnp(signed_hnp):
            return {
                "success": False,
                "error_code": "HNP_NOT_IN_HAP",
                "stdout": combined_stdout,
                "stderr": f"signed HAP does not contain hnp/*.hnp: {signed_hnp}",
                "output_path": None,
            }

        return {
            "success": True,
            "error_code": None,
            "stdout": combined_stdout,
            "stderr": combined_stderr,
            "output_path": str(signed_hnp),
            "artifact_source": "hnp_direct",
            "sign_status": "signed",
        }
