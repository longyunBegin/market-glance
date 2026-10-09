import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_units_use_current_install_path_and_tunnel_is_opt_in(self):
        with tempfile.TemporaryDirectory() as temporary:
            systemd_dir = Path(temporary) / "units"
            mock_bin = Path(temporary) / "bin"
            mock_bin.mkdir()
            log = Path(temporary) / "systemctl.log"
            mock_systemctl = mock_bin / "systemctl"
            mock_systemctl.write_text(
                "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\nexit 0\n",
                encoding="utf-8",
            )
            mock_systemctl.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "SYSTEMD_DIR": str(systemd_dir),
                "SYSTEMCTL": str(mock_systemctl),
                "SYSTEMCTL_LOG": str(log),
                "ENABLE_TUNNEL": "0",
                "START_FETCH": "0",
                "HTTPS_PROXY": "",
            })
            subprocess.run(["bash", str(REPO / "systemd" / "install.sh")],
                           cwd=REPO, env=env, check=True, capture_output=True, text=True)
            for unit in ("market-glance-fetch.service", "market-glance-www.service",
                         "market-glance-healthcheck.service"):
                text = (systemd_dir / unit).read_text(encoding="utf-8")
                self.assertIn(str(REPO), text)
                self.assertNotIn("/home/hatch/workspace", text)
                self.assertNotIn("@APP_DIR@", text)
            tunnel = (systemd_dir / "market-glance-tunnel.service").read_text(encoding="utf-8")
            self.assertIn(str(REPO / "tunnel.sh"), tunnel)
            self.assertNotIn("tunnel-local.sh", tunnel)
            calls = log.read_text(encoding="utf-8")
            self.assertNotIn("enable --now market-glance-tunnel.service", calls)


if __name__ == "__main__":
    unittest.main()
