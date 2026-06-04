"""Wrapper around the DevEco hvigor build toolchain."""

import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from harmonyos_dev_mcp.build.artifact_finder import (
    BuildArtifactFinder,
    build_output_resolution_guidance,
    is_fresh_output,
    resolve_sign_status,
)
from harmonyos_dev_mcp.build.packaging_hnp import HnpPackager, hap_contains_hnp
from harmonyos_dev_mcp.build.packaging_hsp import HspPackager, hap_contains_hsp, path_inside
from harmonyos_dev_mcp.build.signing import (
    SigningHelper,
    extract_array_objects,
    extract_compatible_version,
    extract_named_array_object,
    extract_object_value,
    extract_scalar_value,
    find_matching_token,
    looks_like_deveco_encrypted_password,
    merge_outputs,
    resolve_module_root,
    resolve_profile_relative_path,
)
from harmonyos_dev_mcp.build.toolchain_discovery import (
    ToolchainDiscovery,
    has_java_executable,
    is_writable_dir,
)
from harmonyos_dev_mcp.config import Config


class HvigorWrapper:
    """Run hvigor commands for a HarmonyOS project."""

    def __init__(self, project_path: str, deveco_path: Optional[str] = None):
        self.project_path = Path(project_path).resolve()
        if not self.project_path.exists():
            raise ValueError(f"project path does not exist: {project_path}")

        self.artifact_finder = BuildArtifactFinder(self.project_path)
        self.toolchain_discovery = ToolchainDiscovery(
            self.project_path,
            system_name=platform.system(),
            which=shutil.which,
            writable_dir=self._is_writable_dir,
        )
        self.deveco_path = self._find_deveco_studio(deveco_path)
        if not self.deveco_path:
            raise ValueError(
                "unable to locate DevEco Studio; install it or pass deveco_path explicitly"
            )

        self.node_exe = self._find_node_executable()
        self.hvigorw_js = self._find_hvigor_wrapper()
        self.sdk_root = self._find_sdk_root()
        self.java_home = self._find_java_home()
        self.hvigor_user_home = self._resolve_hvigor_user_home()
        self.signing_helper = SigningHelper(
            self.project_path,
            self.sdk_root,
            self.java_home,
            build_env=self._build_command_env,
            command_runner=subprocess.run,
            system_name=platform.system(),
            which=shutil.which,
        )
        self.hnp_packager = HnpPackager(self.project_path, self.signing_helper)
        self.hsp_packager = HspPackager(self.project_path, self.signing_helper)

        if not self.node_exe.exists():
            raise ValueError(f"node executable not found: {self.node_exe}")
        if not self.hvigorw_js.exists():
            raise ValueError(f"hvigor wrapper not found: {self.hvigorw_js}")
        if not self.sdk_root.exists():
            raise ValueError(f"HarmonyOS SDK root not found: {self.sdk_root}")
        if self.java_home and not self.java_home.exists():
            raise ValueError(f"JAVA_HOME not found: {self.java_home}")

        logger.info("Initialized HvigorWrapper")
        logger.info(f"  project_path: {self.project_path}")
        logger.info(f"  deveco_path: {self.deveco_path}")
        logger.info(f"  node_exe: {self.node_exe}")
        logger.info(f"  hvigorw_js: {self.hvigorw_js}")
        logger.info(f"  sdk_root: {self.sdk_root}")
        if self.java_home:
            logger.info(f"  java_home: {self.java_home}")
        logger.info(f"  hvigor_user_home: {self.hvigor_user_home}")

    @staticmethod
    def _is_writable_dir(path: Path) -> bool:
        return is_writable_dir(path)

    def _resolve_hvigor_user_home(self) -> Path:
        return self.toolchain_discovery.resolve_hvigor_user_home()

    def _find_deveco_studio(self, custom_path: Optional[str] = None) -> Optional[Path]:
        return self.toolchain_discovery.find_deveco_studio(custom_path)

    def _find_node_executable(self) -> Path:
        return self.toolchain_discovery.find_node_executable(self.deveco_path)

    def _find_hvigor_wrapper(self) -> Path:
        return self.toolchain_discovery.find_hvigor_wrapper(self.deveco_path)

    def _find_sdk_root(self) -> Path:
        return self.toolchain_discovery.find_sdk_root(self.deveco_path)

    @staticmethod
    def _has_java_executable(candidate: Path, java_names: List[str]) -> bool:
        return has_java_executable(candidate, java_names)

    def _find_java_home(self) -> Optional[Path]:
        return self.toolchain_discovery.find_java_home(self.deveco_path)

    def _build_command_env(self, include_hvigor_home: bool = False) -> Dict[str, str]:
        env = os.environ.copy()
        env["DEVECO_SDK_HOME"] = str(self.sdk_root)
        if include_hvigor_home:
            env["HVIGOR_USER_HOME"] = str(self.hvigor_user_home)
        if self.java_home:
            env["JAVA_HOME"] = str(self.java_home)
            env["PATH"] = f"{self.java_home / 'bin'}{os.pathsep}{env.get('PATH', '')}"
        return env

    def _execute_command(self, args: List[str], timeout: int = None) -> Dict[str, Any]:
        """Execute hvigor with the resolved toolchain and environment."""
        effective_args = list(args)
        if (
            platform.system() == "Windows"
            and "--no-daemon" not in effective_args
            and "--daemon" not in effective_args
        ):
            effective_args.append("--no-daemon")

        cmd = [str(self.node_exe), str(self.hvigorw_js)] + effective_args
        timeout = timeout or Config.BUILD_TIMEOUT

        logger.debug(f"running hvigor command: {' '.join(cmd)}")

        env = self._build_command_env(include_hvigor_home=True)

        self.hvigor_user_home.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=timeout,
                env=env,
                close_fds=True,
            )
            command_success = result.returncode == 0 and not self._has_build_failure_output(
                result.stdout, result.stderr
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": command_success,
            }
        except subprocess.TimeoutExpired:
            logger.error(f"hvigor command timed out after {timeout}s")
            return {
                "error_code": "BUILD_TIMEOUT",
                "stdout": "",
                "stderr": f"build timed out after {timeout}s",
                "success": False,
            }
        except Exception as exc:
            logger.error(f"failed to execute hvigor command: {exc}")
            return {
                "error_code": "BUILD_COMMAND_ERROR",
                "stdout": "",
                "stderr": str(exc),
                "success": False,
            }
        finally:
            self._cleanup_hvigor_user_home()

    @staticmethod
    def _has_build_failure_output(stdout: str, stderr: str) -> bool:
        combined = f"{stdout}\n{stderr}".upper()
        return "BUILD FAILED" in combined or "COMPILE RESULT:FAIL" in combined

    def _cleanup_hvigor_user_home(self) -> None:
        """Remove the per-build HVIGOR_USER_HOME directory."""
        try:
            shutil.rmtree(self.hvigor_user_home, ignore_errors=False)
        except FileNotFoundError:
            return
        except Exception as exc:
            logger.warning(f"failed to remove hvigor_user_home {self.hvigor_user_home}: {exc}")

    def clean(self, product: str = "default", module_name: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"clean build outputs for product={product}")
        args = [
            "--no-daemon",
            "clean",
            "-p",
            f"product={product}",
            "--analyze=normal",
            "--parallel",
        ]
        if module_name:
            args.extend(["--mode", "module", "-p", f"module={module_name}"])
        result = self._execute_command(args)
        if result["success"]:
            logger.info("clean succeeded")
        else:
            logger.error(f"clean failed: {result['stderr']}")
        return result

    @staticmethod
    def _is_fresh_output(path: Optional[Path], not_before: Optional[float]) -> bool:
        return is_fresh_output(path, not_before)

    def _build_profile_paths(self) -> List[Path]:
        profiles: List[Path] = []
        root_profile = self.project_path / "build-profile.json5"
        if root_profile.exists():
            profiles.append(root_profile)

        for path in self.project_path.rglob("build-profile.json5"):
            if path == root_profile:
                continue
            lowered_parts = {part.lower() for part in path.parts}
            if lowered_parts & {"build", ".git", ".venv", "__pycache__"}:
                continue
            profiles.append(path)
        return profiles

    @staticmethod
    def _looks_like_signing_path(value: str) -> bool:
        lowered = value.lower()
        if lowered.startswith(("http://", "https://")):
            return False
        if "\\" in value or "/" in value:
            return True
        return lowered.endswith(
            (".p7b", ".p12", ".cer", ".jks", ".keystore", ".pfx", ".pem", ".der", ".mobileprovision")
        )

    def _find_missing_signing_files(self, profile_paths: List[Path]) -> List[str]:
        missing: List[str] = []
        key_pattern = re.compile(
            r'(?i)["\']?(storefile|keystorefile|keystore|storepath|certpath|certfile|profile)["\']?\s*:\s*["\']([^"\']+)["\']'
        )
        for profile_path in profile_paths:
            try:
                content = profile_path.read_text(encoding="utf-8")
            except OSError:
                continue
            for _, raw_value in key_pattern.findall(content):
                value = raw_value.strip()
                if not self._looks_like_signing_path(value):
                    continue
                candidates = []
                path_value = Path(value)
                if path_value.is_absolute():
                    candidates.append(path_value)
                else:
                    candidates.append((profile_path.parent / path_value).resolve())
                    candidates.append((self.project_path / path_value).resolve())
                if any(candidate.exists() for candidate in candidates):
                    continue
                missing.append(value)
        return sorted(set(missing))

    def _validate_build_config(
        self,
        target: str,
        build_mode: str,
        product: str,
        module_name: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        profile_paths = self._build_profile_paths()
        if not profile_paths:
            return {
                "error_code": "BUILD_PROFILE_MISSING",
                "stdout": "",
                "stderr": "build-profile.json5 not found in project",
                "success": False,
                "output_path": None,
            }

        if target == "har":
            return None

        combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in profile_paths)
        if build_mode and re.search(r"(?i)\bbuildModeSet\b", combined):
            if not re.search(rf'(?i)"name"\s*:\s*"{re.escape(build_mode)}"', combined):
                return {
                    "error_code": "INVALID_BUILD_MODE",
                    "stdout": "",
                    "stderr": f'build mode "{build_mode}" is not declared in build-profile.json5',
                    "success": False,
                    "output_path": None,
                }

        product_signing_match = re.search(
            rf'(?is)"name"\s*:\s*"{re.escape(product)}".*?"signingConfig"\s*:\s*"([^"]+)"',
            combined,
        )
        if not product_signing_match:
            return None

        signing_name = product_signing_match.group(1)
        if not re.search(rf'(?is)"name"\s*:\s*"{re.escape(signing_name)}"', combined):
            return {
                "error_code": "SIGNING_CONFIG_MISSING",
                "stdout": "",
                "stderr": f'signing config "{signing_name}" referenced by product "{product}" was not found',
                "success": False,
                "output_path": None,
            }

        missing_files = self._find_missing_signing_files(profile_paths)
        if missing_files:
            return {
                "error_code": "SIGNING_FILE_NOT_FOUND",
                "stdout": "",
                "stderr": (
                    "signing files referenced by build-profile.json5 were not found: "
                    + ", ".join(missing_files)
                ),
                "success": False,
                "output_path": None,
            }

        logger.debug(
            f"validated build config for target={target}, build_mode={build_mode}, product={product}, module_name={module_name or ''}"
        )
        return None

    def _extract_output_path_from_logs(
        self,
        stdout: str,
        stderr: str,
        output_type: str,
        not_before: Optional[float] = None,
    ) -> Optional[Path]:
        return self.artifact_finder.extract_output_path_from_logs(
            stdout,
            stderr,
            output_type,
            not_before=not_before,
        )

    def _find_output_from_metadata(
        self,
        output_type: str,
        product: str,
        module_name: Optional[str],
        not_before: Optional[float] = None,
    ) -> Optional[Path]:
        return self.artifact_finder.find_output_from_metadata(
            output_type,
            product,
            module_name,
            not_before=not_before,
        )

    def _find_sign_fallback_script(self, build_mode: str) -> Optional[Path]:
        candidates = [
            self.project_path / "hapsigner" / f"2-{build_mode}-sign.bat",
            self.project_path / "hapsigner" / f"sign-{build_mode}.bat",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _run_sign_fallback(self, build_mode: str) -> Dict[str, Any]:
        script_path = self._find_sign_fallback_script(build_mode)
        if script_path is None:
            return {
                "success": False,
                "error_code": "SIGN_FALLBACK_SCRIPT_MISSING",
                "stdout": "",
                "stderr": f"sign fallback script not found for build_mode={build_mode}",
                "output_path": None,
            }

        expected_output = script_path.parent / "signApp.hap"
        if expected_output.exists():
            expected_output.unlink(missing_ok=True)

        existing_outputs = {
            path.resolve()
            for path in script_path.parent.glob("*.hap")
            if path.is_file()
        }

        runner_path = script_path.parent / f".mcp-sign-{build_mode}.bat"
        try:
            original_script = script_path.read_text(encoding="utf-8", errors="ignore")
            runner_lines = [line for line in original_script.splitlines() if line.strip().lower() != "pause"]
            runner_path.write_text("\n".join(runner_lines) + "\n", encoding="utf-8")

            result = subprocess.run(
                ["cmd.exe", "/c", str(runner_path)],
                cwd=str(script_path.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=Config.BUILD_TIMEOUT,
                env=self._build_command_env(),
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error_code": "SIGN_FALLBACK_TIMEOUT",
                "stdout": "",
                "stderr": f"sign fallback timed out after {Config.BUILD_TIMEOUT}s",
                "output_path": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "error_code": "SIGN_FALLBACK_ERROR",
                "stdout": "",
                "stderr": str(exc),
                "output_path": None,
            }
        finally:
            runner_path.unlink(missing_ok=True)

        signed_output = self._extract_output_path_from_logs(
            result.stdout,
            result.stderr,
            "hap",
        )
        if signed_output is None:
            signed_output = self._resolve_sign_fallback_output(script_path.parent, existing_outputs, expected_output)
        success = result.returncode == 0 and signed_output is not None
        return {
            "success": success,
            "error_code": None if success else "SIGN_FALLBACK_FAILED",
            "stdout": result.stdout.replace("Press any key to continue . . .", "").strip(),
            "stderr": result.stderr.replace("Press any key to continue . . .", "").strip(),
            "output_path": str(signed_output) if signed_output else None,
            "artifact_source": "sign_fallback" if success else None,
        }

    @staticmethod
    def _resolve_sign_fallback_output(
        output_dir: Path,
        existing_outputs: set[Path],
        expected_output: Path,
    ) -> Optional[Path]:
        if expected_output.exists():
            return expected_output

        candidates = [
            path.resolve()
            for path in output_dir.glob("*.hap")
            if path.is_file() and path.resolve() not in existing_outputs
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0]

    @staticmethod
    def _resolve_sign_status(output_path: Optional[Path]) -> str:
        return resolve_sign_status(output_path)

    def _score_output_path(
        self,
        path: Path,
        output_type: str,
        build_mode: str,
        product: str,
        module_name: Optional[str],
    ) -> tuple[int, float]:
        return self.artifact_finder.score_output_path(
            path,
            output_type,
            build_mode,
            product,
            module_name,
        )

    @staticmethod
    def _is_test_artifact(path: Path) -> bool:
        return BuildArtifactFinder.is_test_artifact(path)

    @staticmethod
    def _build_output_resolution_guidance(*, stale_logged_output: bool = False) -> str:
        return build_output_resolution_guidance(stale_logged_output=stale_logged_output)

    @staticmethod
    def _hap_contains_hnp(path: Path) -> bool:
        return hap_contains_hnp(path)

    @staticmethod
    def _hap_contains_hsp(path: Path) -> bool:
        return hap_contains_hsp(path)

    @staticmethod
    def _find_matching_token(text: str, start: int, open_token: str, close_token: str) -> Optional[int]:
        return find_matching_token(text, start, open_token, close_token)

    @classmethod
    def _extract_array_objects(cls, content: str, key: str) -> List[str]:
        return extract_array_objects(content, key)

    @staticmethod
    def _extract_scalar_value(content: str, key: str) -> Optional[str]:
        return extract_scalar_value(content, key)

    @classmethod
    def _extract_object_value(cls, content: str, key: str) -> Optional[str]:
        return extract_object_value(content, key)

    @classmethod
    def _extract_named_array_object(cls, content: str, array_key: str, name: str) -> Optional[str]:
        return extract_named_array_object(content, array_key, name)

    @staticmethod
    def _resolve_profile_relative_path(raw_value: str, profile_path: Path, project_path: Path) -> Path:
        return resolve_profile_relative_path(raw_value, profile_path, project_path)

    @staticmethod
    def _extract_compatible_version(product_object: str) -> str:
        return extract_compatible_version(product_object)

    def _resolve_repack_signing_config(self, product: str, error_prefix: str) -> Dict[str, Any]:
        return self.signing_helper.resolve_repack_signing_config(
            self._build_profile_paths(),
            product,
            error_prefix,
        )

    def _resolve_module_root(self, module_name: Optional[str]) -> Path:
        return resolve_module_root(self.project_path, self._build_profile_paths(), module_name)

    @staticmethod
    def _contains_hnp_package(path: Path) -> bool:
        return HnpPackager.contains_hnp_package(path)

    @staticmethod
    def _hnp_root_for_package(package_path: Path) -> Path:
        return HnpPackager.hnp_root_for_package(package_path)

    def _find_hnp_source_root(self, module_root: Path) -> Optional[Path]:
        return self.hnp_packager.find_source_root(module_root)

    def _discover_shared_modules(self) -> List[str]:
        return self.hsp_packager.discover_shared_modules(self._build_profile_paths())

    @staticmethod
    def _path_inside(path: Path, root: Path) -> bool:
        return path_inside(path, root)

    def _stage_hnp_source(self, source_root: Path, outputs_root: Path, module_root: Path) -> Path:
        return self.hnp_packager.stage_source(source_root, outputs_root, module_root)

    def _stage_hsp_outputs(self, hsp_paths: List[Path], outputs_root: Path, module_root: Path) -> Path:
        return self.hsp_packager.stage_outputs(hsp_paths, outputs_root, module_root)

    def _merge_hsp_pack_info(
        self,
        base_pack_info: Path,
        hsp_paths: List[Path],
        outputs_root: Path,
        module_root: Path,
    ) -> Dict[str, Any]:
        return self.hsp_packager.merge_pack_info(
            base_pack_info,
            hsp_paths,
            outputs_root,
            module_root,
        )

    def _find_toolchain_jar(self, jar_name: str) -> Optional[Path]:
        return self.signing_helper.find_toolchain_jar(jar_name)

    def _java_command(self) -> str:
        return self.signing_helper.java_command()

    def _run_packaging_command(self, cmd: List[str], error_prefix: str) -> Dict[str, Any]:
        return self.signing_helper.run_packaging_command(cmd, error_prefix)

    @staticmethod
    def _merge_outputs(*parts: Optional[str]) -> str:
        return merge_outputs(*parts)

    @staticmethod
    def _looks_like_deveco_encrypted_password(value: str) -> bool:
        return looks_like_deveco_encrypted_password(value)

    def _password_candidates(self, signing: Dict[str, Any]) -> List[tuple[str, str]]:
        return self.signing_helper.password_candidates(signing)

    def _build_hnp_sign_command(
        self,
        java: str,
        hap_sign_tool: Path,
        unsigned_hnp: Path,
        signed_hnp: Path,
        signing: Dict[str, Any],
        key_password: str,
        keystore_password: str,
    ) -> List[str]:
        return self.signing_helper.build_hap_sign_command(
            java,
            hap_sign_tool,
            unsigned_hnp,
            signed_hnp,
            signing,
            key_password,
            keystore_password,
        )

    def _run_base_hap_build_for_repack(
        self,
        build_mode: str,
        product: str,
        module_name: Optional[str],
        is_clean: bool,
        purpose: str,
    ) -> Dict[str, Any]:
        if is_clean:
            clean_result = self.clean(product=product, module_name=module_name)
            if not clean_result["success"]:
                return {
                    "success": False,
                    "error_code": clean_result.get("error_code", "CLEAN_FAILED"),
                    "stdout": clean_result.get("stdout", ""),
                    "stderr": clean_result.get("stderr", "clean failed"),
                    "output_path": None,
                }

        logger.info(f"build base HAP for {purpose} packaging product={product}")
        args: List[str] = [
            "--no-daemon",
            "--mode",
            "module",
            "-p",
            f"product={product}",
            "-p",
            f"buildMode={build_mode}",
        ]
        if module_name:
            args.extend(["-p", f"module={module_name}"])
        args.extend(["assembleHap", "--analyze=normal", "--parallel", "--incremental"])
        result = self._execute_command(args)
        if not result["success"]:
            result["output_path"] = None
            logger.error(f"base HAP build for {purpose} failed: {result['stderr']}")
        return result

    def _repack_and_sign_hnp(
        self,
        module_root: Path,
        hnp_source_root: Path,
        product: str,
        signing: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.hnp_packager.repack_and_sign(
            module_root,
            hnp_source_root,
            product,
            signing,
        )

    def _build_hnp(
        self,
        build_mode: str,
        product: str,
        module_name: Optional[str],
        is_clean: bool,
    ) -> Dict[str, Any]:
        base_result = self._run_base_hap_build_for_repack(
            build_mode,
            product,
            module_name,
            is_clean,
            "HNP",
        )
        if not base_result.get("success"):
            return base_result

        module_root = self._resolve_module_root(module_name)
        hnp_source_root = self._find_hnp_source_root(module_root)
        if hnp_source_root is None:
            return {
                "error_code": "HNP_PACKAGE_NOT_FOUND",
                "stdout": base_result.get("stdout", ""),
                "stderr": (
                    "target=hnp requires built HNP packages under a module hnp directory, "
                    f"for example {module_root / 'hnp'} containing ABI subdirectories with .hnp files"
                ),
                "success": False,
                "output_path": None,
            }

        signing = self._resolve_repack_signing_config(product, "HNP")
        if not signing.get("success"):
            return {
                "success": False,
                "error_code": signing["error_code"],
                "stdout": base_result.get("stdout", ""),
                "stderr": self._merge_outputs(base_result.get("stderr"), signing["stderr"]),
                "output_path": None,
            }

        result = self._repack_and_sign_hnp(module_root, hnp_source_root, product, signing)
        result["stdout"] = self._merge_outputs(base_result.get("stdout"), result.get("stdout"))
        result["stderr"] = self._merge_outputs(base_result.get("stderr"), result.get("stderr"))
        if result.get("success"):
            logger.info(f"HNP build succeeded: {result['output_path']}")
        else:
            logger.error(f"HNP build failed: {result.get('stderr', '')}")

        return result

    def _build_hsp_outputs(
        self,
        build_mode: str,
        product: str,
        hsp_module_names: Optional[List[str]],
    ) -> Dict[str, Any]:
        modules = self._resolve_hsp_module_names(hsp_module_names)
        if not modules:
            modules = self._discover_shared_modules()
        if not modules:
            return {
                "success": False,
                "error_code": "HSP_MODULE_NOT_FOUND",
                "stdout": "",
                "stderr": (
                    "include_hsp=true requires at least one shared module. Pass hsp_module_names "
                    "or add modules whose src/main/module.json5 declares "
                    'type="shared".'
                ),
                "output_paths": [],
            }

        outputs: List[Path] = []
        stdout_parts: List[str] = []
        stderr_parts: List[str] = []
        for module in modules:
            result = self.build(
                target="hsp",
                build_mode=build_mode,
                product=product,
                module_name=module,
                is_clean=False,
                include_hsp=False,
            )
            if not result.get("success") and result.get("error_code") in {
                "BUILD_OUTPUT_NOT_FOUND",
                "STALE_BUILD_ARTIFACT",
            }:
                logger.info(f"retry HSP module build with clean because output was not refreshed: {module}")
                retry_result = self.build(
                    target="hsp",
                    build_mode=build_mode,
                    product=product,
                    module_name=module,
                    is_clean=True,
                    include_hsp=False,
                )
                if retry_result.get("success"):
                    result = retry_result
                else:
                    retry_result["stdout"] = self._merge_outputs(
                        result.get("stdout"),
                        retry_result.get("stdout"),
                    )
                    retry_result["stderr"] = self._merge_outputs(
                        result.get("stderr"),
                        retry_result.get("stderr"),
                    )
                    result = retry_result
            stdout_parts.append(result.get("stdout", ""))
            stderr_parts.append(result.get("stderr", ""))
            if not result.get("success"):
                return {
                    "success": False,
                    "error_code": result.get("error_code", "HSP_BUILD_FAILED"),
                    "stdout": self._merge_outputs(*stdout_parts),
                    "stderr": self._merge_outputs(*stderr_parts),
                    "output_paths": [],
                }
            output_path = result.get("output_path")
            if not output_path:
                return {
                    "success": False,
                    "error_code": "HSP_OUTPUT_NOT_FOUND",
                    "stdout": self._merge_outputs(*stdout_parts),
                    "stderr": f"HSP build completed but no output path was returned for module {module}",
                    "output_paths": [],
                }
            outputs.append(Path(output_path))

        return {
            "success": True,
            "stdout": self._merge_outputs(*stdout_parts),
            "stderr": self._merge_outputs(*stderr_parts),
            "output_paths": outputs,
        }

    @staticmethod
    def _resolve_hsp_module_names(hsp_module_names: Optional[List[str]]) -> List[str]:
        return HspPackager.resolve_module_names(hsp_module_names)

    def _repack_and_sign_hap_with_hsp(
        self,
        module_root: Path,
        hsp_paths: List[Path],
        product: str,
        signing: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self.hsp_packager.repack_and_sign(
            module_root,
            hsp_paths,
            product,
            signing,
        )

    def _build_hap_with_hsp(
        self,
        build_mode: str,
        product: str,
        module_name: Optional[str],
        hsp_module_names: Optional[List[str]],
        is_clean: bool,
    ) -> Dict[str, Any]:
        base_result = self._run_base_hap_build_for_repack(
            build_mode,
            product,
            module_name,
            is_clean,
            "HSP",
        )
        if not base_result.get("success"):
            return base_result

        hsp_result = self._build_hsp_outputs(
            build_mode,
            product,
            hsp_module_names,
        )
        if not hsp_result.get("success"):
            return {
                **hsp_result,
                "stdout": self._merge_outputs(base_result.get("stdout"), hsp_result.get("stdout")),
                "stderr": self._merge_outputs(base_result.get("stderr"), hsp_result.get("stderr")),
                "output_path": None,
            }

        module_root = self._resolve_module_root(module_name)
        signing = self._resolve_repack_signing_config(product, "HSP")
        if not signing.get("success"):
            return {
                "success": False,
                "error_code": signing["error_code"],
                "stdout": self._merge_outputs(base_result.get("stdout"), hsp_result.get("stdout")),
                "stderr": self._merge_outputs(
                    base_result.get("stderr"),
                    hsp_result.get("stderr"),
                    signing["stderr"],
                ),
                "output_path": None,
            }

        result = self._repack_and_sign_hap_with_hsp(
            module_root,
            hsp_result["output_paths"],
            product,
            signing,
        )
        result["hsp_output_paths"] = [str(path) for path in hsp_result["output_paths"]]
        result["stdout"] = self._merge_outputs(
            base_result.get("stdout"),
            hsp_result.get("stdout"),
            result.get("stdout"),
        )
        result["stderr"] = self._merge_outputs(
            base_result.get("stderr"),
            hsp_result.get("stderr"),
            result.get("stderr"),
        )
        if result.get("success"):
            logger.info(f"HSP-integrated HAP build succeeded: {result['output_path']}")
        else:
            logger.error(f"HSP-integrated HAP build failed: {result.get('stderr', '')}")
        return result

    def build(
        self,
        target: str = "hap",
        build_mode: str = "debug",
        product: str = "default",
        module_name: Optional[str] = None,
        is_clean: bool = False,
        include_hsp: bool = False,
        hsp_module_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if target not in {"hap", "har", "hsp", "app", "hnp"}:
            return {
                "error_code": "INVALID_BUILD_TARGET",
                "stdout": "",
                "stderr": 'target must be one of "hap", "har", "hsp", "app", or "hnp"',
                "success": False,
                "output_path": None,
            }
        if target in {"har", "hsp"} and not module_name:
            return {
                "error_code": "MISSING_MODULE_NAME",
                "stdout": "",
                "stderr": f'module_name is required when target="{target}"',
                "success": False,
                "output_path": None,
            }

        validation_error = self._validate_build_config(target, build_mode, product, module_name)
        if validation_error is not None:
            return validation_error

        if target == "hnp":
            return self._build_hnp(build_mode, product, module_name, is_clean)
        if target == "hap" and include_hsp:
            return self._build_hap_with_hsp(
                build_mode,
                product,
                module_name,
                hsp_module_names,
                is_clean,
            )

        build_started_at = time.time()
        if is_clean:
            clean_result = self.clean(
                product=product,
                module_name=module_name if target in {"hap", "har", "hsp"} else None,
            )
            if not clean_result["success"]:
                return {
                    "success": False,
                    "error_code": clean_result.get("error_code", "CLEAN_FAILED"),
                    "stdout": clean_result.get("stdout", ""),
                    "stderr": clean_result.get("stderr", "clean failed"),
                    "output_path": None,
                }

        logger.info(f"build {target.upper()} for product={product}")
        args: List[str] = ["--no-daemon"]
        if target in {"hap", "har", "hsp"}:
            args.extend(["--mode", "module"])
        args.extend(["-p", f"product={product}", "-p", f"buildMode={build_mode}"])
        if target in {"har", "hsp"} and module_name:
            args.extend(["-p", f"module={module_name}"])
        args.extend(
            [
                {"hap": "assembleHap", "har": "assembleHar", "hsp": "assembleHsp", "app": "assembleApp"}[target],
                "--analyze=normal",
                "--parallel",
                "--incremental",
            ]
        )
        result = self._execute_command(args)
        if result["success"]:
            logged_output = None
            artifact_source = ""
            sign_status = "unknown"
            output_path = self._find_output_from_metadata(target, product, module_name, not_before=build_started_at)
            if output_path is not None:
                artifact_source = "metadata"
                sign_status = self._resolve_sign_status(output_path)
            if output_path is None:
                logged_output = self._extract_output_path_from_logs(
                    result.get("stdout", ""),
                    result.get("stderr", ""),
                    target,
                )
                output_path = self._extract_output_path_from_logs(
                    result.get("stdout", ""),
                    result.get("stderr", ""),
                    target,
                    not_before=build_started_at,
                )
                if output_path is not None:
                    artifact_source = "logs"
                    sign_status = self._resolve_sign_status(output_path)
            if output_path is None:
                output_path = self._find_build_output(
                    target,
                    build_mode,
                    product,
                    module_name,
                    not_before=build_started_at,
                )
                if output_path is not None:
                    artifact_source = "scan"
                    sign_status = self._resolve_sign_status(output_path)
            if output_path is None and logged_output is not None and not self._is_fresh_output(logged_output, build_started_at):
                return {
                    "success": False,
                    "error_code": "STALE_BUILD_ARTIFACT",
                    "stdout": result.get("stdout", ""),
                    "stderr": self._build_output_resolution_guidance(stale_logged_output=True),
                    "output_path": None,
                }
            if output_path is None:
                output_path = self._find_build_output(
                    target,
                    build_mode,
                    product,
                    module_name,
                )
                if output_path is not None:
                    artifact_source = "cached_scan"
                    sign_status = self._resolve_sign_status(output_path)
            if output_path is None:
                return {
                    "success": False,
                    "error_code": "BUILD_OUTPUT_NOT_FOUND",
                    "stdout": result.get("stdout", ""),
                    "stderr": self._build_output_resolution_guidance(),
                    "output_path": None,
                }
            if (
                target == "hap"
                and output_path is not None
                and "unsigned" in output_path.name.lower()
            ):
                fallback_result = self._run_sign_fallback(build_mode)
                if fallback_result["success"]:
                    output_path = Path(fallback_result["output_path"])
                    result["stdout"] = f"{result.get('stdout', '')}\n{fallback_result.get('stdout', '')}".strip()
                    result["stderr"] = f"{result.get('stderr', '')}\n{fallback_result.get('stderr', '')}".strip()
                    artifact_source = fallback_result.get("artifact_source", "sign_fallback")
                    sign_status = "signed"
                elif fallback_result.get("error_code") != "SIGN_FALLBACK_SCRIPT_MISSING":
                    return {
                        "success": False,
                        "error_code": fallback_result["error_code"],
                        "stdout": f"{result.get('stdout', '')}\n{fallback_result.get('stdout', '')}".strip(),
                        "stderr": (
                            f"{result.get('stderr', '')}\n{fallback_result.get('stderr', '')}"
                        ).strip(),
                        "output_path": None,
                    }
            result["output_path"] = str(output_path) if output_path else None
            result["artifact_source"] = artifact_source or None
            result["sign_status"] = sign_status
            logger.info(f"{target.upper()} build succeeded: {result['output_path']}")
        else:
            result["output_path"] = None
            logger.error(f"{target.upper()} build failed: {result['stderr']}")
        return result

    def _find_build_output(
        self,
        output_type: str,
        build_mode: str = "debug",
        product: str = "default",
        module_name: Optional[str] = None,
        not_before: Optional[float] = None,
    ) -> Optional[Path]:
        return self.artifact_finder.find_build_output(
            output_type,
            build_mode=build_mode,
            product=product,
            module_name=module_name,
            not_before=not_before,
        )
