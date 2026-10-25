import Flutter
import UIKit
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
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // TSBackgroundFetch registers its BGTaskScheduler handlers itself in +load;
    // registering them again here aborts with "already been registered".

    // Observer queries must be registered on every launch, including the
    // background launches HealthKit triggers for new data. Wake-ups are
    // queued until the Dart side reports ready.
    HealthBackgroundDelivery.shared.start()

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  // With the UIScene lifecycle (required since iOS 27) the engine is created
  // by the scene's FlutterViewController, so plugins and channels are wired up here.
  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    let messenger = engineBridge.applicationRegistrar.messenger()
    setupDeviceLockChannel(messenger: messenger)
    HealthBackgroundDelivery.shared.attach(messenger: messenger)
  }

  private func setupDeviceLockChannel(messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "com.cherep.device_state/lock_state",
      binaryMessenger: messenger
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
