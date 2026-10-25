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
  /// Runs Dart during background launches (HealthKit, BGTask), where no scene
  /// connects and therefore no implicit engine is created.
  private var backgroundEngine: FlutterEngine?

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

    // A foreground launch connects its scene right after this returns.
    DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
      self?.startBackgroundEngineIfNeeded()
    }

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  private func startBackgroundEngineIfNeeded() {
    guard backgroundEngine == nil, UIApplication.shared.connectedScenes.isEmpty else { return }
    let engine = FlutterEngine(name: "background", project: nil, allowHeadlessExecution: true)
    guard engine.run(withEntrypoint: "backgroundMain") else { return }
    GeneratedPluginRegistrant.register(with: engine)
    setupDeviceLockChannel(messenger: engine.binaryMessenger)
    HealthBackgroundDelivery.shared.attach(messenger: engine.binaryMessenger)
    backgroundEngine = engine
  }

  // With the UIScene lifecycle (required since iOS 27) the engine is created
  // by the scene's FlutterViewController, so plugins and channels are wired up here.
  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    // Tear down the background engine before the UI engine's plugins attach:
    // background_fetch removes its shared listener when an engine detaches.
    backgroundEngine?.destroyContext()
    backgroundEngine = nil

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
