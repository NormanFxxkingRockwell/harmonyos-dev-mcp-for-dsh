from pathlib import Path

from harmonyos_dev_mcp.build.toolchain_discovery import ToolchainDiscovery
from harmonyos_dev_mcp.config import Config


def _write_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _clear_config_paths(monkeypatch) -> None:
    monkeypatch.setattr(Config, "NODE_PATH", None)
    monkeypatch.setattr(Config, "HVIGOR_PATH", None)
    monkeypatch.setattr(Config, "HARMONYOS_SDK_PATH", None)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.delenv("JDK_HOME", raising=False)


def test_windows_layout_is_detected(tmp_path, monkeypatch):
    project = tmp_path / "MyApplication"
    project.mkdir()
    deveco = tmp_path / "DevEco Studio"
    node = deveco / "tools" / "node" / "node.exe"
    hvigor = deveco / "tools" / "hvigor" / "bin" / "hvigorw.js"
    sdk = deveco / "sdk"
    java_home = deveco / "jbr"
    _write_file(node)
    _write_file(hvigor)
    _write_file(sdk / "default" / "sdk-pkg.json", "{}")
    _write_file(java_home / "bin" / "java.exe")

    _clear_config_paths(monkeypatch)
    monkeypatch.setattr(Config, "DEVECO_STUDIO_PATH", str(deveco))
    discovery = ToolchainDiscovery(project, system_name="Windows", which=lambda name: None)

    assert discovery.find_deveco_studio() == deveco
    assert discovery.find_node_executable(deveco) == node
    assert discovery.find_hvigor_wrapper(deveco) == hvigor
    assert discovery.find_sdk_root(deveco) == sdk
    assert discovery.find_java_home(deveco) == java_home


def test_macos_bundle_layout_is_detected(tmp_path, monkeypatch):
    project = tmp_path / "MyApplication"
    project.mkdir()
    deveco = tmp_path / "DevEco-Studio.app"
    node = deveco / "Contents" / "tools" / "node" / "bin" / "node"
    hvigor = deveco / "Contents" / "tools" / "hvigor" / "bin" / "hvigorw.js"
    sdk = deveco / "Contents" / "sdk"
    java_home = deveco / "Contents" / "jbr" / "Contents" / "Home"
    _write_file(node)
    _write_file(hvigor)
    _write_file(sdk / "default" / "sdk-pkg.json", "{}")
    _write_file(java_home / "bin" / "java")

    _clear_config_paths(monkeypatch)
    monkeypatch.setattr(Config, "DEVECO_STUDIO_PATH", str(deveco))
    discovery = ToolchainDiscovery(project, system_name="Darwin", which=lambda name: None)

    assert discovery.find_deveco_studio() == deveco
    assert discovery.find_node_executable(deveco) == node
    assert discovery.find_hvigor_wrapper(deveco) == hvigor
    assert discovery.find_sdk_root(deveco) == sdk
    assert discovery.find_java_home(deveco) == java_home


def test_linux_layout_is_detected(tmp_path, monkeypatch):
    project = tmp_path / "MyApplication"
    project.mkdir()
    deveco = tmp_path / "DevEco-Studio"
    node = deveco / "tools" / "node" / "node"
    hvigor = deveco / "tools" / "hvigor" / "bin" / "hvigorw.js"
    sdk = deveco / "sdk"
    java_home = deveco / "jbr"
    _write_file(node)
    _write_file(hvigor)
    _write_file(sdk / "default" / "sdk-pkg.json", "{}")
    _write_file(java_home / "bin" / "java")

    _clear_config_paths(monkeypatch)
    monkeypatch.setattr(Config, "DEVECO_STUDIO_PATH", str(deveco))
    discovery = ToolchainDiscovery(project, system_name="Linux", which=lambda name: None)

    assert discovery.find_deveco_studio() == deveco
    assert discovery.find_node_executable(deveco) == node
    assert discovery.find_hvigor_wrapper(deveco) == hvigor
    assert discovery.find_sdk_root(deveco) == sdk
    assert discovery.find_java_home(deveco) == java_home


def test_hvigor_user_home_falls_back_to_temp_dir(tmp_path):
    project = tmp_path / "MyApplication"
    project.mkdir()
    temp_dir = tmp_path / "temp"

    def writable_dir(path: Path) -> bool:
        return ".hvigor" not in path.parts

    discovery = ToolchainDiscovery(project, writable_dir=writable_dir, temp_dir=temp_dir)

    result = discovery.resolve_hvigor_user_home()

    assert result.parent == temp_dir / "harmonyos_dev_mcp" / "hvigor_home"
