import Flutter
import UIKit
import BackgroundTasks
import TSBackgroundFetch
import Foundation
import Darwin

private final class DeviceLockMonitor {
  static let shared = DeviceLockMonitor()

  private var notificationToken: Int32 = 0
  private var isLocked: Bool = false
  private let stateQueue = DispatchQueue(
    label: "com.cherep.device_state.lock_monitor",
    attributes: .concurrent
  )

  private init() {
    startMonitoringLockState()
  }

  func currentLockState() -> Bool {
    stateQueue.sync { isLocked }
  }

  private func startMonitoringLockState() {
    var token: Int32 = 0
    let status = notify_register_dispatch(
      "com.apple.springboard.lockstate",
      &token,
      DispatchQueue.main
    ) { [weak self] notificationToken in
      self?.refreshLockState(token: notificationToken)
    }

    notificationToken = token

    if status == NOTIFY_STATUS_OK {
      refreshLockState(token: token)
    } else {
      // Fallback to protected data availability as a conservative estimate.
      updateLockState(isLocked: !UIApplication.shared.isProtectedDataAvailable)
    }
  }

  private func refreshLockState(token: Int32) {
    var state: UInt64 = 0
    let status = notify_get_state(token, &state)
    if status == NOTIFY_STATUS_OK {
      // Any non-zero state means the device is locked.
      updateLockState(isLocked: state != 0)
    } else {
      updateLockState(isLocked: !UIApplication.shared.isProtectedDataAvailable)
    }
  }

  private func updateLockState(isLocked: Bool) {
    stateQueue.async(flags: .barrier) { [weak self] in
      self?.isLocked = isLocked
    }
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
    setupDeviceLockChannel()
    setupHealthBackgroundDelivery()

    return flutterInitialized
  }

  private func setupHealthBackgroundDelivery() {
    guard let registrar = self.registrar(forPlugin: "HealthBackgroundDelivery") else { return }
    HealthBackgroundDelivery.shared.attach(messenger: registrar.messenger())
    // Observer queries must be registered on every launch, including the
    // background launches HealthKit triggers for new data.
    HealthBackgroundDelivery.shared.start()
  }

  private func setupDeviceLockChannel() {
    guard let registrar = self.registrar(forPlugin: "DeviceLockChannel") else {
      assertionFailure("Flutter registrar unavailable; cannot set up method channel")
      return
    }

    let channel = FlutterMethodChannel(
      name: "com.cherep.device_state/lock_state",
      binaryMessenger: registrar.messenger()
    )

    channel.setMethodCallHandler { call, result in
      switch call.method {
      case "isDeviceLocked":
        result(DeviceLockMonitor.shared.currentLockState())
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }
}
