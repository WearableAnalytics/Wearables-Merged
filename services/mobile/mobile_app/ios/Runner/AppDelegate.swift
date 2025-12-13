import Flutter
import UIKit
import BackgroundTasks
import TSBackgroundFetch

private final class ProtectedDataMonitor {
  static let shared = ProtectedDataMonitor()
  private var isAvailable: Bool

  private init() {
    isAvailable = UIApplication.shared.isProtectedDataAvailable

    NotificationCenter.default.addObserver(
      forName: UIApplication.protectedDataWillBecomeUnavailableNotification,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      self?.isAvailable = false
    }

    NotificationCenter.default.addObserver(
      forName: UIApplication.protectedDataDidBecomeAvailableNotification,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      self?.isAvailable = true
    }
  }

  func currentAvailability() -> Bool {
    // Always read the system value in case we missed notifications while suspended.
    isAvailable = UIApplication.shared.isProtectedDataAvailable
    return isAvailable
  }
}

@main
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // Ensure Flutter sets up the window/rootViewController before we grab it.
    let flutterInitialized = super.application(application, didFinishLaunchingWithOptions: launchOptions)
    GeneratedPluginRegistrant.register(with: self)

    // Register background-fetch task handler for BGTaskScheduler (required to simulate/handle "com.transistorsoft.fetch").
    if #available(iOS 13.0, *) {
      // Register the app-refresh task identifier used by flutter_background_fetch
      TSBackgroundFetch.sharedInstance().registerAppRefreshTask()
    }

    // Use the Flutter plugin registrar rather than the rootViewController; the latter is not guaranteed
    // to be available in didFinishLaunchingWithOptions once UISceneDelegate is enabled.
    guard let registrar = self.registrar(forPlugin: "ProtectedDataChannel") else {
      assertionFailure("Flutter registrar unavailable; cannot set up method channel")
      return flutterInitialized
    }

    let channel = FlutterMethodChannel(
      name: "com.cherep.device_state/protected_data",
      binaryMessenger: registrar.messenger()
    )

    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "isProtectedDataAvailable":
        result(ProtectedDataMonitor.shared.currentAvailability())
      default:
        result(FlutterMethodNotImplemented)
      }
    }

    return flutterInitialized
  }
}
