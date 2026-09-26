import SwiftUI

@main
struct NeuroWatchConnectApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    @StateObject private var bluetooth = BluetoothSyncManager()

    var body: some View {
        VStack(spacing: 22) {
            Image(systemName: "watchface.applewatch.case")
                .font(.system(size: 48, weight: .light))
                .foregroundStyle(Color(red: 0.20, green: 0.34, blue: 0.32))

            Text("NEUROWATCH")
                .font(.system(size: 27, weight: .bold, design: .rounded))
                .tracking(2)

            Text("Синхронизация времени")
                .font(.system(size: 19, weight: .medium))

            Text("На часах открой меню → SYNC PHONE TIME")
                .font(.system(size: 15))
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .padding(.top, 4)

            Text(bluetooth.status)
                .font(.system(size: 16, weight: .medium))
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, minHeight: 88)
                .padding(16)
                .background(.white.opacity(0.76), in: RoundedRectangle(cornerRadius: 18))

            Button {
                bluetooth.startSync()
            } label: {
                HStack(spacing: 10) {
                    if bluetooth.isSyncing { ProgressView().tint(.white) }
                    Text(bluetooth.isSyncing ? "Подключаю часы…" : "Синхронизировать сейчас")
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .tint(Color(red: 0.20, green: 0.34, blue: 0.32))
            .disabled(bluetooth.isSyncing)

            if bluetooth.isSyncing {
                Button("Отменить") { bluetooth.cancel() }
                    .buttonStyle(.bordered)
            }

            Text("Передаются текущие дата, время и часовой пояс iPhone. Для Екатеринбурга используется UTC+5, если он выбран в настройках телефона.")
                .font(.system(size: 13))
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .padding(.top, 6)
        }
        .padding(24)
        .foregroundStyle(Color(red: 0.12, green: 0.16, blue: 0.16))
        .background(Color(red: 0.96, green: 0.95, blue: 0.91).ignoresSafeArea())
    }
}
