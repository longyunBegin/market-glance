import plistlib
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MACOS = REPO / "macos"
WIDGET = MACOS / "widget"


class WidgetKitSupportTests(unittest.TestCase):
    def test_widgetkit_project_and_required_sources_are_present(self):
        project = WIDGET / "MarketGlance.xcodeproj" / "project.pbxproj"
        self.assertTrue(project.is_file())
        self.assertTrue((WIDGET / "MarketGlanceApp.swift").is_file())
        self.assertTrue((WIDGET / "MarketGlanceWidget.swift").is_file())
        contents = project.read_text(encoding="utf-8")
        self.assertIn("com.apple.product-type.app-extension", contents)
        self.assertIn("MarketGlanceWidgetExtension.appex in Embed App Extensions", contents)
        self.assertIn("MACOSX_DEPLOYMENT_TARGET = 14.0", contents)

    def test_app_opens_local_dashboard_in_native_webview(self):
        source = (WIDGET / "MarketGlanceApp.swift").read_text(encoding="utf-8")
        self.assertIn("import WebKit", source)
        self.assertIn('WindowGroup("Market Glance")', source)
        self.assertIn("WKWebView", source)
        self.assertIn(r"http://127.0.0.1:\(port)/", source)
        self.assertIn("DashboardUnavailableView", source)
        self.assertNotIn("NSWorkspace.shared.open", source)

    def test_widget_reads_only_local_quote_snapshot_and_supports_two_sizes(self):
        source = (WIDGET / "MarketGlanceWidget.swift").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:\\(port)/data/quotes.json", source)
        self.assertIn("@Environment(\\.widgetFamily)", source)
        self.assertIn(".supportedFamilies([.systemSmall, .systemMedium])", source)
        self.assertIn("scheme == .dark ? .black", source)
        self.assertIn(".after(nextRefresh)", source)
        self.assertNotIn("APCA_API_KEY_ID", source)
        self.assertNotIn("APCA_API_SECRET_KEY", source)

    def test_app_and_widget_have_local_network_client_sandbox_only(self):
        app = plistlib.loads((WIDGET / "App.entitlements").read_bytes())
        extension = plistlib.loads((WIDGET / "Widget.entitlements").read_bytes())
        for entitlements in (app, extension):
            self.assertIs(entitlements["com.apple.security.app-sandbox"], True)
            self.assertIs(entitlements["com.apple.security.network.client"], True)
            self.assertEqual(len(entitlements), 2)

        widget_info = plistlib.loads((WIDGET / "Widget-Info.plist").read_bytes())
        self.assertEqual(
            widget_info["NSExtension"]["NSExtensionPointIdentifier"],
            "com.apple.widgetkit-extension",
        )
        self.assertIn("$(MARKET_GLANCE_API_PORT)", widget_info["MarketGlanceAPIPort"])

    def test_widget_install_script_is_valid_and_injects_port(self):
        script = MACOS / "install-widget.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        source = script.read_text(encoding="utf-8")
        self.assertIn("xcodebuild", source)
        self.assertIn('MARKET_GLANCE_API_PORT="$PORT"', source)
        self.assertIn('"$HOME/Applications/Market Glance.app"', source)
        self.assertIn("macOS 14", source)

    def test_full_installer_copies_and_invokes_widget_build_when_xcode_exists(self):
        installer = (MACOS / "install.sh").read_text(encoding="utf-8")
        self.assertIn('cp -R "$SRC/macos/widget" "$APP_DIR/macos/widget"', installer)
        self.assertIn('bash "$APP_DIR/macos/install-widget.sh" "$PORT"', installer)
        self.assertIn("if command -v xcodebuild", installer)
        self.assertLess(installer.index('for _ in $(seq 1 30)'), installer.index("if command -v xcodebuild"))
        self.assertIn("Market Glance.app", (MACOS / "uninstall.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
