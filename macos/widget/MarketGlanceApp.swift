import AppKit
import SwiftUI
import WidgetKit

@main
struct MarketGlanceApp: App {
    var body: some Scene {
        WindowGroup {
            DashboardView()
                .frame(minWidth: 420, minHeight: 270)
        }
        .windowResizability(.contentSize)
    }
}

private struct DashboardView: View {
    @State private var refreshMessage = ""

    private var port: Int {
        let value = Bundle.main.object(forInfoDictionaryKey: "MarketGlanceAPIPort")
        return (value as? String).flatMap(Int.init) ?? (value as? Int) ?? 8090
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 12) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 25, weight: .semibold))
                    .foregroundStyle(.green)
                VStack(alignment: .leading, spacing: 3) {
                    Text("Market Glance")
                        .font(.system(size: 22, weight: .semibold))
                    Text("macOS 行情小组件")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }

            Text("在桌面或通知中心添加“Market Glance 行情”小组件，即可查看观察池中的最新价格和涨跌幅。小组件从本机行情服务读取快照，不会访问或保存行情源密钥。")
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 10) {
                Button("打开行情看板") {
                    if let url = URL(string: "http://127.0.0.1:\(port)/") {
                        NSWorkspace.shared.open(url)
                    }
                }
                .buttonStyle(.borderedProminent)

                Button("刷新小组件") {
                    WidgetCenter.shared.reloadAllTimelines()
                    refreshMessage = "已请求刷新；macOS 可能会按系统计划延后更新。"
                }
                .buttonStyle(.bordered)
            }

            if !refreshMessage.isEmpty {
                Text(refreshMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Label("更新频率由 macOS WidgetKit 管理，并非实时推送。", systemImage: "clock")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(26)
    }
}
