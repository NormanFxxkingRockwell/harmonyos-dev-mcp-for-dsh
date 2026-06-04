"""Signing and SDK packaging command helpers."""

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from harmonyos_dev_mcp.config import Config


CommandRunner = Callable[..., Any]
BuildEnvFactory = Callable[[], dict[str, str]]
WhichFn = Callable[[str], Optional[str]]


def find_matching_token(text: str, start: int, open_token: str, close_token: str) -> Optional[int]:
    depth = 0
    quote: Optional[str] = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == open_token:
            depth += 1
        elif char == close_token:
            depth -= 1
            if depth == 0:
                return index
    return None


def extract_array_objects(content: str, key: str) -> list[str]:
    pattern = re.compile(rf'(?is)["\']?{re.escape(key)}["\']?\s*:\s*\[')
    match = pattern.search(content)
    if not match:
        return []

    array_start = content.find("[", match.start())
    array_end = find_matching_token(content, array_start, "[", "]")
    if array_end is None:
        return []

    array_content = content[array_start + 1 : array_end]
    objects: list[str] = []
    search_from = 0
    while True:
        object_start = array_content.find("{", search_from)
        if object_start < 0:
            break
        object_end = find_matching_token(array_content, object_start, "{", "}")
        if object_end is None:
            break
        objects.append(array_content[object_start : object_end + 1])
        search_from = object_end + 1
    return objects


def extract_scalar_value(content: str, key: str) -> Optional[str]:
    pattern = re.compile(
        rf'(?is)["\']?{re.escape(key)}["\']?\s*:\s*'
        r'(?:"([^"]*)"|\'([^\']*)\'|([^,\n\r}]+))'
    )
    match = pattern.search(content)
    if not match:
        return None
    value = next(group for group in match.groups() if group is not None)
    return value.strip().rstrip(",")


def extract_object_value(content: str, key: str) -> Optional[str]:
    pattern = re.compile(rf'(?is)["\']?{re.escape(key)}["\']?\s*:\s*\{{')
    match = pattern.search(content)
    if not match:
        return None
    object_start = content.find("{", match.start())
    object_end = find_matching_token(content, object_start, "{", "}")
    if object_end is None:
        return None
    return content[object_start : object_end + 1]


def extract_named_array_object(content: str, array_key: str, name: str) -> Optional[str]:
    for item in extract_array_objects(content, array_key):
        if extract_scalar_value(item, "name") == name:
            return item
    return None


def resolve_profile_relative_path(raw_value: str, profile_path: Path, project_path: Path) -> Path:
    path_value = Path(raw_value).expanduser()
    if path_value.is_absolute():
        return path_value

    candidates = [
        (profile_path.parent / path_value).resolve(),
        (project_path / path_value).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def extract_compatible_version(product_object: str) -> str:
    for key in ("compatibleSdkVersion", "targetSdkVersion"):
        value = extract_scalar_value(product_object, key)
        if not value:
            continue
        parenthesized = re.search(r"\((\d+)\)", value)
        if parenthesized:
            return parenthesized.group(1)
        numeric = re.search(r"\b(\d+)\b", value)
        if numeric:
            return numeric.group(1)
    return "9"


def resolve_module_root(project_path: Path, profile_paths: list[Path], module_name: Optional[str]) -> Path:
    module = module_name or "entry"
    candidates = [
        project_path / module,
        project_path / "harmony" / "app" / module,
        project_path / "app" / module,
    ]
    for profile_path in profile_paths:
        try:
            content = profile_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for module_object in extract_array_objects(content, "modules"):
            name = extract_scalar_value(module_object, "name")
            if name != module:
                continue
            src_path = extract_scalar_value(module_object, "srcPath")
            if src_path:
                candidates.insert(0, (profile_path.parent / src_path).resolve())

    for candidate in candidates:
        if (candidate / "src" / "main" / "module.json5").exists() or (candidate / "build").exists():
            return candidate.resolve()
    return candidates[0].resolve()


def merge_outputs(*parts: Optional[str]) -> str:
    return "\n".join(part.strip() for part in parts if part and part.strip())


def looks_like_deveco_encrypted_password(value: str) -> bool:
    return len(value) >= 32 and re.fullmatch(r"[0-9A-Fa-f]+", value) is not None


class SigningHelper:
    """Resolve signing config and run SDK packaging/signing tools."""

    def __init__(
        self,
        project_path: Path,
        sdk_root: Path,
        java_home: Optional[Path],
        *,
        build_env: BuildEnvFactory,
        command_runner: CommandRunner = subprocess.run,
        system_name: Optional[str] = None,
        which: Optional[WhichFn] = None,
    ):
        self.project_path = Path(project_path).resolve()
        self.sdk_root = Path(sdk_root).resolve()
        self.java_home = Path(java_home).resolve() if java_home else None
        self.build_env = build_env
        self.command_runner = command_runner
        self.system_name = system_name or os.name
        self.which = which or shutil.which

    def resolve_repack_signing_config(
        self,
        profile_paths: list[Path],
        product: str,
        error_prefix: str,
    ) -> dict[str, Any]:
        for profile_path in profile_paths:
            try:
                content = profile_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            product_object = extract_named_array_object(content, "products", product)
            if product_object is None:
                continue

            signing_name = extract_scalar_value(product_object, "signingConfig")
            if not signing_name:
                return {
                    "success": False,
                    "error_code": f"{error_prefix}_SIGNING_CONFIG_MISSING",
                    "stderr": f'product "{product}" does not declare signingConfig',
                }

            signing_object = extract_named_array_object(content, "signingConfigs", signing_name)
            if signing_object is None:
                return {
                    "success": False,
                    "error_code": f"{error_prefix}_SIGNING_CONFIG_MISSING",
                    "stderr": f'signing config "{signing_name}" referenced by product "{product}" was not found',
                }

            material = extract_object_value(signing_object, "material") or signing_object
            scalar_keys = ["keyAlias", "keyPassword", "storePassword", "certpath", "profile", "storeFile"]
            values = {key: extract_scalar_value(material, key) for key in scalar_keys}
            missing = [key for key, value in values.items() if value is None]
            if missing:
                return {
                    "success": False,
                    "error_code": f"{error_prefix}_SIGNING_CONFIG_INCOMPLETE",
                    "stderr": "signing material is missing required keys: " + ", ".join(missing),
                }

            path_keys = {
                "certpath": "app_cert_file",
                "profile": "profile_file",
                "storeFile": "keystore_file",
            }
            resolved_paths = {
                output_key: resolve_profile_relative_path(values[input_key], profile_path, self.project_path)
                for input_key, output_key in path_keys.items()
            }
            missing_paths = [str(path) for path in resolved_paths.values() if not path.exists()]
            if missing_paths:
                return {
                    "success": False,
                    "error_code": f"{error_prefix}_SIGNING_FILE_NOT_FOUND",
                    "stderr": "signing files were not found: " + ", ".join(missing_paths),
                }

            return {
                "success": True,
                "key_alias": values["keyAlias"],
                "key_password": values["keyPassword"],
                "keystore_password": values["storePassword"],
                "sign_alg": extract_scalar_value(material, "signAlg") or "SHA256withECDSA",
                "compatible_version": extract_compatible_version(product_object),
                **resolved_paths,
            }

        return {
            "success": False,
            "error_code": f"{error_prefix}_SIGNING_CONFIG_MISSING",
            "stderr": f'product "{product}" was not found in build-profile.json5',
        }

    def find_toolchain_jar(self, jar_name: str) -> Optional[Path]:
        candidates = [
            self.sdk_root / "default" / "openharmony" / "toolchains" / "lib" / jar_name,
            self.sdk_root / "openharmony" / "toolchains" / "lib" / jar_name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        for candidate in self.sdk_root.rglob(jar_name):
            if candidate.is_file():
                return candidate
        return None

    def java_command(self) -> str:
        java_name = "java.exe" if self.system_name == "Windows" else "java"
        if self.java_home:
            candidate = self.java_home / "bin" / java_name
            if candidate.exists():
                return str(candidate)
        resolved = self.which(java_name) or self.which("java")
        return resolved or java_name

    def run_packaging_command(self, cmd: list[str], error_prefix: str) -> dict[str, Any]:
        try:
            result = self.command_runner(
                cmd,
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=Config.BUILD_TIMEOUT,
                env=self.build_env(),
                close_fds=True,
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error_code": f"{error_prefix}_TIMEOUT",
                "stdout": "",
                "stderr": f"{error_prefix} command timed out after {Config.BUILD_TIMEOUT}s",
            }
        except Exception as exc:
            return {
                "success": False,
                "error_code": f"{error_prefix}_ERROR",
                "stdout": "",
                "stderr": str(exc),
            }

        return {
            "success": result.returncode == 0,
            "error_code": None if result.returncode == 0 else f"{error_prefix}_FAILED",
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    @staticmethod
    def password_candidates(signing: dict[str, Any]) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []

        def add(key_password: Optional[str], store_password: Optional[str]) -> None:
            if key_password is None or store_password is None:
                return
            pair = (key_password, store_password)
            if pair not in candidates:
                candidates.append(pair)

        add(signing["key_password"], signing["keystore_password"])

        env_key_password = os.getenv("HAP_KEY_PASSWORD")
        env_store_password = os.getenv("HAP_STORE_PASSWORD")
        if env_key_password or env_store_password:
            add(
                env_key_password or signing["key_password"],
                env_store_password or signing["keystore_password"],
            )

        shared_password = os.getenv("HAP_SIGN_PASSWORD")
        if shared_password:
            add(shared_password, shared_password)

        if (
            looks_like_deveco_encrypted_password(signing["key_password"])
            or looks_like_deveco_encrypted_password(signing["keystore_password"])
        ):
            add("123456", "123456")

        return candidates

    @staticmethod
    def build_hap_sign_command(
        java: str,
        hap_sign_tool: Path,
        unsigned_hap: Path,
        signed_hap: Path,
        signing: dict[str, Any],
        key_password: str,
        keystore_password: str,
    ) -> list[str]:
        return [
            java,
            "-jar",
            str(hap_sign_tool),
            "sign-app",
            "-mode",
            "localSign",
            "-keyAlias",
            signing["key_alias"],
            "-keyPwd",
            key_password,
            "-appCertFile",
            str(signing["app_cert_file"]),
            "-profileFile",
            str(signing["profile_file"]),
            "-inFile",
            str(unsigned_hap),
            "-signAlg",
            signing["sign_alg"],
            "-keystoreFile",
            str(signing["keystore_file"]),
            "-keystorePwd",
            keystore_password,
            "-outFile",
            str(signed_hap),
            "-compatibleVersion",
            signing["compatible_version"],
            "-signCode",
            "1",
        ]
