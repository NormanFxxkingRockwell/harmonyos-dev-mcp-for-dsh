"""HSP packaging helpers."""

import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .signing import SigningHelper, extract_array_objects, extract_scalar_value, merge_outputs


def hap_contains_hsp(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.startswith("shared_libs/") and name.endswith(".hsp") for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class HspPackager:
    """Repack and sign HAPs with HSP payloads."""

    def __init__(self, project_path: Path, signing_helper: SigningHelper):
        self.project_path = Path(project_path).resolve()
        self.signing_helper = signing_helper

    def discover_shared_modules(self, profile_paths: list[Path]) -> list[str]:
        modules: list[str] = []
        for profile_path in profile_paths:
            try:
                content = profile_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for module_object in extract_array_objects(content, "modules"):
                name = extract_scalar_value(module_object, "name")
                src_path = extract_scalar_value(module_object, "srcPath")
                if not name or not src_path:
                    continue
                module_json = profile_path.parent / src_path / "src" / "main" / "module.json5"
                if not module_json.exists():
                    continue
                try:
                    module_content = module_json.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if re.search(r'(?is)["\']?type["\']?\s*:\s*["\']shared["\']', module_content):
                    modules.append(name)

        if not modules:
            for module_json in self.project_path.glob("*/src/main/module.json5"):
                try:
                    module_content = module_json.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if re.search(r'(?is)["\']?type["\']?\s*:\s*["\']shared["\']', module_content):
                    modules.append(module_json.parents[2].name)

        return sorted(set(modules))

    @staticmethod
    def stage_outputs(hsp_paths: list[Path], outputs_root: Path, module_root: Path) -> Path:
        staging_root = (outputs_root / "shared_libs").resolve()
        if not path_inside(staging_root, module_root):
            raise ValueError(f"refusing to stage HSP packages outside module root: {staging_root}")

        if staging_root.exists():
            shutil.rmtree(staging_root)
        staging_root.mkdir(parents=True, exist_ok=True)
        for hsp_path in hsp_paths:
            shutil.copy2(hsp_path, staging_root / hsp_path.name)
        return staging_root

    @staticmethod
    def merge_pack_info(
        base_pack_info: Path,
        hsp_paths: list[Path],
        outputs_root: Path,
        module_root: Path,
    ) -> dict[str, Any]:
        merged_pack_info = (outputs_root / "hsp_pack_info" / "pack.info").resolve()
        if not path_inside(merged_pack_info, module_root):
            return {
                "success": False,
                "error_code": "HSP_PACK_INFO_ERROR",
                "stderr": f"refusing to write merged pack.info outside module root: {merged_pack_info}",
            }

        try:
            merged = json.loads(base_pack_info.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "success": False,
                "error_code": "HSP_PACK_INFO_ERROR",
                "stderr": f"failed to read base pack.info: {exc}",
            }

        summary = merged.setdefault("summary", {})
        merged_modules = summary.setdefault("modules", [])
        merged_packages = merged.setdefault("packages", [])
        module_names = {
            module.get("distro", {}).get("moduleName")
            for module in merged_modules
            if isinstance(module, dict)
        }
        package_names = {
            package.get("name")
            for package in merged_packages
            if isinstance(package, dict)
        }

        for hsp_path in hsp_paths:
            try:
                with zipfile.ZipFile(hsp_path) as archive:
                    hsp_pack = json.loads(archive.read("pack.info").decode("utf-8"))
            except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
                return {
                    "success": False,
                    "error_code": "HSP_PACK_INFO_ERROR",
                    "stderr": f"failed to read pack.info from HSP {hsp_path}: {exc}",
                }

            for module in hsp_pack.get("summary", {}).get("modules", []):
                module_name = module.get("distro", {}).get("moduleName") if isinstance(module, dict) else None
                if module_name and module_name not in module_names:
                    merged_modules.append(module)
                    module_names.add(module_name)
            for package in hsp_pack.get("packages", []):
                package_name = package.get("name") if isinstance(package, dict) else None
                if package_name and package_name not in package_names:
                    merged_packages.append(package)
                    package_names.add(package_name)

        try:
            merged_pack_info.parent.mkdir(parents=True, exist_ok=True)
            merged_pack_info.write_text(
                json.dumps(merged, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except OSError as exc:
            return {
                "success": False,
                "error_code": "HSP_PACK_INFO_ERROR",
                "stderr": f"failed to write merged pack.info: {exc}",
            }

        return {"success": True, "pack_info": merged_pack_info}

    @staticmethod
    def resolve_module_names(hsp_module_names: Optional[list[str]]) -> list[str]:
        modules: list[str] = []

        for raw_value in hsp_module_names or []:
            if not raw_value:
                continue
            module = raw_value.strip()
            if module and module not in modules:
                modules.append(module)
        return modules

    def repack_and_sign(
        self,
        module_root: Path,
        hsp_paths: list[Path],
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
                "error_code": "HSP_TOOLCHAIN_NOT_FOUND",
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
                "error_code": "HSP_PACKAGING_INPUT_MISSING",
                "stdout": "",
                "stderr": "HSP packaging inputs were not found: " + ", ".join(missing_inputs),
                "output_path": None,
            }

        outputs.mkdir(parents=True, exist_ok=True)
        shared_libs_root = self.stage_outputs(hsp_paths, outputs, module_root)
        merged_pack_info = self.merge_pack_info(
            packaging_inputs["pack_info"],
            hsp_paths,
            outputs,
            module_root,
        )
        if not merged_pack_info.get("success"):
            return {
                "success": False,
                "error_code": merged_pack_info["error_code"],
                "stdout": "",
                "stderr": merged_pack_info["stderr"],
                "output_path": None,
            }
        module = module_root.name
        unsigned_hap = outputs / f"{module}-{product}-unsigned-hsp.hap"
        signed_hap = outputs / f"{module}-{product}-signed-hsp.hap"
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
            str(unsigned_hap),
            "--shared-libs-path",
            str(shared_libs_root),
            "--index-path",
            str(packaging_inputs["index"]),
            "--pack-info-path",
            str(merged_pack_info["pack_info"]),
            "--pkg-context-path",
            str(packaging_inputs["pkg_context"]),
            "--force",
            "true",
        ]
        if lib_path.exists():
            pack_cmd.extend(["--lib-path", str(lib_path)])

        logger.info(f"repacking HAP with HSP packages from {shared_libs_root}")
        pack_result = self.signing_helper.run_packaging_command(pack_cmd, "HSP_REPACK")
        if not pack_result["success"] or not unsigned_hap.exists():
            return {
                **pack_result,
                "output_path": None,
                "error_code": pack_result.get("error_code") or "HSP_REPACK_FAILED",
            }

        logger.info(f"signing HAP with HSP packages: {signed_hap}")
        sign_failures: list[dict[str, Any]] = []
        successful_sign_result: Optional[dict[str, Any]] = None
        for key_password, keystore_password in self.signing_helper.password_candidates(signing):
            signed_hap.unlink(missing_ok=True)
            sign_cmd = self.signing_helper.build_hap_sign_command(
                java,
                hap_sign_tool,
                unsigned_hap,
                signed_hap,
                signing,
                key_password,
                keystore_password,
            )
            sign_result = self.signing_helper.run_packaging_command(sign_cmd, "HSP_SIGN")
            if sign_result["success"] and signed_hap.exists():
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
                "error_code": last_failure.get("error_code") or "HSP_SIGN_FAILED",
                "stdout": combined_stdout,
                "stderr": combined_stderr,
                "output_path": None,
            }

        combined_stdout = merge_outputs(
            pack_result.get("stdout"),
            successful_sign_result.get("stdout"),
        )
        combined_stderr = merge_outputs(
            pack_result.get("stderr"),
            successful_sign_result.get("stderr"),
        )
        if not hap_contains_hsp(signed_hap):
            return {
                "success": False,
                "error_code": "HSP_NOT_IN_HAP",
                "stdout": combined_stdout,
                "stderr": f"signed HAP does not contain shared_libs/*.hsp: {signed_hap}",
                "output_path": None,
            }

        return {
            "success": True,
            "error_code": None,
            "stdout": combined_stdout,
            "stderr": combined_stderr,
            "output_path": str(signed_hap),
            "artifact_source": "hsp_direct",
            "sign_status": "signed",
        }
