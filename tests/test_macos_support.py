import json
import plistlib
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MACOS_DIR = REPO / "macos"


class MacOSSupportTests(unittest.TestCase):
    def test_shell_scripts_have_valid_bash_syntax(self):
        for script in sorted(MACOS_DIR.glob("*.sh")):
            with self.subTest(script=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True)

    def test_installer_uses_user_launch_agents_and_preserves_existing_settings(self):
        installer = (MACOS_DIR / "install.sh").read_text(encoding="utf-8")
        self.assertIn('"$HOME/Library/LaunchAgents"', installer)
        self.assertIn('launchctl bootstrap "$DOMAIN"', installer)
        self.assertIn('"KeepAlive": True', installer)
        self.assertIn('"StartInterval": 60', installer)
        self.assertIn('if [[ ! -f "$APP_DIR/config.json" ]]', installer)
        self.assertNotIn("sudo ", installer)

    def test_installer_copies_the_dashboard_entrypoint(self):
        installer = (MACOS_DIR / "install.sh").read_text(encoding="utf-8")
        copy_line = next(line for line in installer.splitlines()
                         if line.startswith("for file in "))
        copied_files = shlex.split(copy_line.removeprefix("for file in ").removesuffix("; do"))
        self.assertIn("index.html", copied_files)

    def test_installer_generates_valid_web_and_fetch_launch_agents(self):
        installer = (MACOS_DIR / "install.sh").read_text(encoding="utf-8")
        generator = installer.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0] + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_dir, agents_dir, log_dir = root / "app", root / "agents", root / "logs"
            agents_dir.mkdir()
            subprocess.run(
                [sys.executable, "-", str(app_dir), str(agents_dir), str(log_dir),
                 sys.executable, str(root)],
                input=generator, text=True, check=True,
            )
            web = plistlib.loads((agents_dir / "io.market-glance.web.plist").read_bytes())
            fetch = plistlib.loads((agents_dir / "io.market-glance.fetch.plist").read_bytes())
        self.assertTrue(web["KeepAlive"])
        self.assertTrue(web["RunAtLoad"])
        self.assertEqual(fetch["StartInterval"], 60)
        self.assertTrue(fetch["RunAtLoad"])
        self.assertTrue(any("run-with-keychain.sh" in arg for arg in web["ProgramArguments"]))
        self.assertTrue(any("run-with-keychain.sh" in arg for arg in fetch["ProgramArguments"]))

    def test_alpaca_credentials_are_read_from_keychain_not_config(self):
        wrapper = (MACOS_DIR / "run-with-keychain.sh").read_text(encoding="utf-8")
        self.assertIn('security find-generic-password', wrapper)
        self.assertIn("Market Glance Alpaca Key ID", wrapper)
        self.assertIn("Market Glance Alpaca Secret Key", wrapper)
        self.assertNotIn("config.json", wrapper)

    def test_chrome_extension_is_minimal_and_local_only(self):
        extension_dir = REPO / "chrome-extension"
        manifest = json.loads((extension_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["action"]["default_popup"], "popup.html")
        self.assertEqual(manifest["host_permissions"], ["http://127.0.0.1/*"])
        self.assertNotIn("permissions", manifest)
        popup = (extension_dir / "popup.js").read_text(encoding="utf-8")
        self.assertIn("const API_PORT = 8090;", popup)
        self.assertIn("textContent", popup)
        self.assertNotIn("innerHTML", popup)

    def test_macos_installer_copies_extension_and_sets_configured_port(self):
        installer = (MACOS_DIR / "install.sh").read_text(encoding="utf-8")
        self.assertIn('cp -R "$SRC/chrome-extension" "$APP_DIR/chrome-extension"', installer)
        self.assertIn('"$APP_DIR/chrome-extension/popup.js" "$PORT"', installer)
        self.assertIn("Chrome 工具栏扩展位于", installer)

        port_script = installer.split("<<'PY'\n", 2)[2].split("\nPY\n", 1)[0] + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            popup = Path(temporary) / "popup.js"
            popup.write_text("const API_PORT = 8090;\n", encoding="utf-8")
            subprocess.run([sys.executable, "-", str(popup), "8123"],
                           input=port_script, text=True, check=True)
            self.assertEqual(popup.read_text(encoding="utf-8"), "const API_PORT = 8123;\n")


if __name__ == "__main__":
    unittest.main()
