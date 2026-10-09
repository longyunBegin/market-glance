import AppKit
import SwiftUI
import WebKit
import WidgetKit

@main
struct MarketGlanceApp: App {
    var body: some Scene {
        WindowGroup("Market Glance") {
            DashboardView()
                .frame(minWidth: 900, minHeight: 620)
        }
        .defaultSize(width: 1280, height: 820)
        .windowResizability(.contentMinSize)
    }
}

private struct DashboardView: View {
    @StateObject private var dashboard = DashboardController()
    @State private var refreshMessage = ""

    private var dashboardURL: URL {
        let value = Bundle.main.object(forInfoDictionaryKey: "MarketGlanceAPIPort")
        let port = (value as? String).flatMap(Int.init) ?? (value as? Int) ?? 8090
        return URL(string: "http://127.0.0.1:\(port)/")!
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.green)
                Text("Market Glance")
                    .font(.system(size: 15, weight: .semibold))

                Spacer()

                if !refreshMessage.isEmpty {
                    Text(refreshMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Button {
                    dashboard.reload()
                } label: {
                    Label("刷新看板", systemImage: "arrow.clockwise")
                }
                .help("重新加载本机行情看板")

                Button {
                    WidgetCenter.shared.reloadAllTimelines()
                    refreshMessage = "已请求刷新小组件；macOS 可能会按系统计划延后更新。"
                } label: {
                    Label("刷新小组件", systemImage: "square.grid.2x2")
                }
                .help("请求 WidgetKit 刷新行情快照")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            Divider()

            ZStack {
                DashboardWebView(controller: dashboard, url: dashboardURL)

                if case .loading = dashboard.loadState, !dashboard.hasLoadedPage {
                    VStack(spacing: 12) {
                        ProgressView()
                        Text("正在连接本机行情看板…")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(.regularMaterial)
                }

                if case .failed(let message) = dashboard.loadState {
                    DashboardUnavailableView(message: message) {
                        dashboard.reload()
                    }
                }
            }
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }
}

private struct DashboardUnavailableView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "wifi.exclamationmark")
                .font(.system(size: 32))
                .foregroundStyle(.secondary)
            Text("无法连接本机看板")
                .font(.title3.weight(.semibold))
            Text("请确认 Market Glance 本机行情服务正在运行，然后重试。")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Text(message)
                .font(.caption.monospaced())
                .foregroundStyle(.tertiary)
                .textSelection(.enabled)
                .multilineTextAlignment(.center)
            Button(action: retry) {
                Label("重试", systemImage: "arrow.clockwise")
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 4)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.regularMaterial)
    }
}

private enum DashboardLoadState {
    case loading
    case loaded
    case failed(String)
}

@MainActor
private final class DashboardController: ObservableObject {
    @Published private(set) var loadState: DashboardLoadState = .loading
    @Published private(set) var hasLoadedPage = false

    private weak var webView: WKWebView?
    private var dashboardURL: URL?

    func attach(_ webView: WKWebView, url: URL) {
        guard self.webView !== webView || dashboardURL != url else { return }
        self.webView = webView
        dashboardURL = url
        load(url, in: webView)
    }

    func reload() {
        guard let webView else { return }
        loadState = .loading
        if webView.url != nil {
            webView.reload()
        } else if let dashboardURL {
            load(dashboardURL, in: webView)
        }
    }

    func navigationDidStart() {
        loadState = .loading
    }

    func navigationDidFinish() {
        hasLoadedPage = true
        loadState = .loaded
    }

    func navigationDidFail(_ error: Error) {
        guard (error as NSError).code != NSURLErrorCancelled else { return }
        loadState = .failed(error.localizedDescription)
    }

    private func load(_ url: URL, in webView: WKWebView) {
        loadState = .loading
        webView.load(URLRequest(url: url, timeoutInterval: 15))
    }
}

private struct DashboardWebView: NSViewRepresentable {
    @ObservedObject var controller: DashboardController
    let url: URL

    func makeCoordinator() -> Coordinator {
        Coordinator(controller: controller)
    }

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        controller.attach(webView, url: url)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        controller.attach(webView, url: url)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        private let controller: DashboardController

        init(controller: DashboardController) {
            self.controller = controller
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            controller.navigationDidStart()
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            controller.navigationDidFinish()
        }

        func webView(
            _ webView: WKWebView,
            didFailProvisionalNavigation navigation: WKNavigation!,
            withError error: Error
        ) {
            controller.navigationDidFail(error)
        }

        func webView(
            _ webView: WKWebView,
            didFail navigation: WKNavigation!,
            withError error: Error
        ) {
            controller.navigationDidFail(error)
        }
    }
}
