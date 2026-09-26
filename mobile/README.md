# NeuroWatch Connect

NeuroWatch Connect synchronizes the watch's date, local time, and UTC offset from the phone. It is separate from the existing USB firmware updater.

## Use

1. On the watch, open **MENU → SYNC PHONE TIME**.
2. Open NeuroWatch Connect on the phone and tap **Synchronize**.
3. Keep the watch on its sync screen until the phone reports success.

The watch's default offset is UTC+05:00 (Yekaterinburg). On synchronization, the phone's current local date/time and current offset replace that setting. After changing the phone's timezone, synchronize again. The watch advertises for at most 60 seconds and disables BLE when the session ends.

## Android build

Open `mobile/android` in Android Studio, or run `gradle :app:testDebugUnitTest :app:assembleDebug` with JDK 17 and Android SDK 35. The APK is produced at `app/build/outputs/apk/debug/app-debug.apk`.

## iPhone build

On a Mac with Xcode and XcodeGen installed, run `xcodegen generate --spec mobile/ios/project.yml` from the repository root, open `mobile/ios/NeuroWatchConnect.xcodeproj`, select a signing team, and run it on the iPhone. The app requires iOS 16 or later and Bluetooth permission.

The `NeuroWatchProtocol` Swift package contains the byte-compatible packet encoder and its golden-vector tests.
