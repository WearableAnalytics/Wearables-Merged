import Flutter
import Foundation
import HealthKit

/// Wakes the app whenever HealthKit stores new samples of the observed types
/// (as often as iOS allows, at most hourly for most types) and asks the Dart
/// side to upload them.
final class HealthBackgroundDelivery {
  static let shared = HealthBackgroundDelivery()

  private let store = HKHealthStore()
  private var channel: FlutterMethodChannel?
  private var started = false
  private var dartReady = false
  private var syncInFlight = false
  private var pending: [HKObserverQueryCompletionHandler] = []

  private var observedTypes: [HKSampleType] {
    let quantities: [HKQuantityTypeIdentifier] = [
      .heartRate,
      .restingHeartRate,
      .walkingHeartRateAverage,
      .heartRateVariabilitySDNN,
      .oxygenSaturation,
      .respiratoryRate,
      .stepCount,
      .distanceWalkingRunning,
      .activeEnergyBurned,
      .appleExerciseTime,
      .bodyMass,
    ]
    var types: [HKSampleType] = quantities.compactMap {
      HKObjectType.quantityType(forIdentifier: $0)
    }
    if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) {
      types.append(sleep)
    }
    types.append(HKObjectType.workoutType())
    return types
  }

  func attach(messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "de.charite.wearables/health_background",
      binaryMessenger: messenger
    )
    channel.setMethodCallHandler { [weak self] call, result in
      switch call.method {
      case "ready":
        self?.dartReady = true
        self?.start()
        self?.flush()
        result(nil)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
    self.channel = channel
  }

  /// Registers observer queries. Must also run during background launches,
  /// so it is called from didFinishLaunching.
  func start() {
    guard HKHealthStore.isHealthDataAvailable(), !started else { return }
    started = true
    for type in observedTypes {
      let query = HKObserverQuery(sampleType: type, predicate: nil) {
        [weak self] _, completion, error in
        DispatchQueue.main.async {
          guard let self, error == nil else {
            completion()
            return
          }
          self.pending.append(completion)
          self.flush()
        }
      }
      store.execute(query)
      store.enableBackgroundDelivery(for: type, frequency: .immediate) { _, _ in }
    }
  }

  /// Runs one upload for all pending wake-ups. HealthKit expects the
  /// completion handlers to be called within its short background budget.
  private func flush() {
    guard dartReady, !syncInFlight, !pending.isEmpty, let channel else { return }
    let handlers = pending
    pending.removeAll()
    syncInFlight = true

    var finished = false
    let finish = { [weak self] in
      guard !finished else { return }
      finished = true
      handlers.forEach { $0() }
      self?.syncInFlight = false
      self?.flush()
    }
    // Progress is saved per day, so an upload cut short here resumes later.
    DispatchQueue.main.asyncAfter(deadline: .now() + 25, execute: finish)
    channel.invokeMethod("newData", arguments: nil) { _ in finish() }
  }
}
