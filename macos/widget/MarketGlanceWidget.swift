import Foundation
import SwiftUI
import WidgetKit

private struct QuotesPayload: Decodable {
    let updated: Double
    let quotes: [MarketQuote]
}

private struct MarketQuote: Decodable, Identifiable {
    let symbol: String
    let name: String
    let group: String
    let price: Double?
    let changePercent: Double?
    let stale: Bool

    var id: String { symbol }

    private enum CodingKeys: String, CodingKey {
        case symbol, name, group, price, stale
        case changePercent = "chg_pct"
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        symbol = try values.decode(String.self, forKey: .symbol)
        name = try values.decodeIfPresent(String.self, forKey: .name) ?? symbol
        group = try values.decodeIfPresent(String.self, forKey: .group) ?? ""
        price = try values.decodeIfPresent(Double.self, forKey: .price)
        changePercent = try values.decodeIfPresent(Double.self, forKey: .changePercent)
        stale = try values.decodeIfPresent(Bool.self, forKey: .stale) ?? false
    }
}

private struct MarketEntry: TimelineEntry {
    let date: Date
    let updatedAt: Date?
    let quotes: [MarketQuote]
    let message: String?

    static var placeholder: MarketEntry {
        MarketEntry(date: Date(), updatedAt: nil, quotes: [], message: nil)
    }
}

private struct QuotesProvider: TimelineProvider {
    func placeholder(in context: Context) -> MarketEntry {
        .placeholder
    }

    func getSnapshot(in context: Context, completion: @escaping (MarketEntry) -> Void) {
        if context.isPreview {
            completion(.placeholder)
            return
        }
        Task { completion(await loadEntry()) }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<MarketEntry>) -> Void) {
        Task {
            let entry = await loadEntry()
            let nextRefresh = Date().addingTimeInterval(5 * 60)
            completion(Timeline(entries: [entry], policy: .after(nextRefresh)))
        }
    }

    private func loadEntry() async -> MarketEntry {
        guard let url = Self.quotesURL else {
            return MarketEntry(date: Date(), updatedAt: nil, quotes: [], message: "本机行情服务未配置")
        }

        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 5)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode) else {
                return MarketEntry(date: Date(), updatedAt: nil, quotes: [], message: "行情暂不可用")
            }
            let payload = try JSONDecoder().decode(QuotesPayload.self, from: data)
            return MarketEntry(
                date: Date(),
                updatedAt: Date(timeIntervalSince1970: payload.updated),
                quotes: payload.quotes,
                message: nil
            )
        } catch {
            return MarketEntry(date: Date(), updatedAt: nil, quotes: [], message: "本机行情服务未连接")
        }
    }

    private static var quotesURL: URL? {
        let rawPort = Bundle.main.object(forInfoDictionaryKey: "MarketGlanceAPIPort")
        let port = (rawPort as? String).flatMap(Int.init) ?? (rawPort as? Int) ?? 8090
        guard (1024...65535).contains(port) else { return nil }
        return URL(string: "http://127.0.0.1:\(port)/data/quotes.json")
    }
}

private enum WidgetPalette {
    static func background(for scheme: ColorScheme) -> Color {
        scheme == .dark ? .black : Color(red: 0.965, green: 0.972, blue: 0.985)
    }

    static func change(_ value: Double?) -> Color {
        guard let value, value.isFinite else { return .secondary }
        if value > 0 { return Color(red: 0.22, green: 0.82, blue: 0.53) }
        if value < 0 { return Color(red: 1.00, green: 0.38, blue: 0.37) }
        return .secondary
    }

    static func price(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "—" }
        return String(format: "%.2f", locale: Locale(identifier: "en_US_POSIX"), value)
    }

    static func percent(_ value: Double?) -> String {
        guard let value, value.isFinite else { return "—" }
        return String(format: "%+.2f%%", locale: Locale(identifier: "en_US_POSIX"), value)
    }
}

private struct MarketCard: View {
    let entry: MarketEntry
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.widgetFamily) private var family

    private var primaryQuote: MarketQuote? {
        entry.quotes.first { $0.price?.isFinite == true } ?? entry.quotes.first
    }

    private var snapshotIsOld: Bool {
        guard let updatedAt = entry.updatedAt else { return false }
        return Date().timeIntervalSince(updatedAt) > 15 * 60
    }

    private var updatedLabel: String {
        guard let updatedAt = entry.updatedAt else { return "等待行情" }
        return updatedAt.formatted(date: .omitted, time: .shortened)
    }

    var body: some View {
        Group {
            if let quote = primaryQuote {
                switchFamilyContent(quote)
            } else {
                unavailableContent
            }
        }
        .containerBackground(for: .widget) {
            WidgetPalette.background(for: colorScheme)
        }
        .widgetURL(Self.dashboardURL)
    }

    @ViewBuilder
    private func switchFamilyContent(_ quote: MarketQuote) -> some View {
        if family == .systemSmall {
            smallCard(quote)
        } else {
            mediumCard(quote)
        }
    }

    private func smallCard(_ quote: MarketQuote) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 5) {
                Text(quote.symbol)
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                    .lineLimit(1)
                Spacer(minLength: 2)
                if quote.stale || snapshotIsOld {
                    Text("延迟")
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.secondary)
                }
            }
            Text(WidgetPalette.price(quote.price))
                .font(.system(size: 30, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .minimumScaleFactor(0.68)
                .lineLimit(1)
            Text(WidgetPalette.percent(quote.changePercent))
                .font(.system(size: 15, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(WidgetPalette.change(quote.changePercent))
            Spacer(minLength: 0)
            HStack(spacing: 4) {
                Circle().fill(WidgetPalette.change(quote.changePercent)).frame(width: 5, height: 5)
                Text(updatedLabel)
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(14)
    }

    private func mediumCard(_ quote: MarketQuote) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(quote.name)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Text(quote.symbol)
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .lineLimit(1)
                    }
                    Text(WidgetPalette.price(quote.price))
                        .font(.system(size: 34, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .minimumScaleFactor(0.7)
                        .lineLimit(1)
                }
                Spacer(minLength: 4)
                VStack(alignment: .trailing, spacing: 5) {
                    Text(WidgetPalette.percent(quote.changePercent))
                        .font(.system(size: 19, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(WidgetPalette.change(quote.changePercent))
                        .lineLimit(1)
                    Text(snapshotIsOld || quote.stale ? "数据较旧" : "更新 \(updatedLabel)")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Rectangle()
                .fill(Color.primary.opacity(colorScheme == .dark ? 0.16 : 0.10))
                .frame(height: 1)

            HStack(alignment: .center, spacing: 0) {
                ForEach(Array(entry.quotes.prefix(5))) { item in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(item.symbol)
                            .font(.system(size: 10, weight: .semibold, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .minimumScaleFactor(0.75)
                        Text(WidgetPalette.percent(item.changePercent))
                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(WidgetPalette.change(item.changePercent))
                            .lineLimit(1)
                            .minimumScaleFactor(0.75)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                if entry.quotes.isEmpty {
                    Text("观察池暂无代码")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.horizontal, 15)
        .padding(.vertical, 12)
    }

    private var unavailableContent: some View {
        VStack(alignment: .leading, spacing: 7) {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(.secondary)
            Text(entry.message ?? "暂无行情")
                .font(.system(size: 14, weight: .semibold))
            Text("打开 Market Glance 检查本机服务")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .padding(15)
    }

    private static var dashboardURL: URL? {
        let rawPort = Bundle.main.object(forInfoDictionaryKey: "MarketGlanceAPIPort")
        let port = (rawPort as? String).flatMap(Int.init) ?? (rawPort as? Int) ?? 8090
        return URL(string: "http://127.0.0.1:\(port)/")
    }
}

struct MarketGlanceWidget: Widget {
    let kind = "MarketGlanceWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: QuotesProvider()) { entry in
            MarketCard(entry: entry)
        }
        .configurationDisplayName("Market Glance 行情")
        .description("查看本机观察池的价格与涨跌幅。")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}

@main
struct MarketGlanceWidgetBundle: WidgetBundle {
    var body: some Widget {
        MarketGlanceWidget()
    }
}
