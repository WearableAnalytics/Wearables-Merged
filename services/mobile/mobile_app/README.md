# wearables_app

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Lab: Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Cookbook: Useful Flutter samples](https://docs.flutter.dev/cookbook)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.


To test background fetch in the iOS simulator, run the following command in terminal:
```
e -l objc -- (void)[[BGTaskScheduler sharedScheduler] _simulateLaunchForTaskWithIdentifier:@"com.transistorsoft.fetch"]
```


## Run app on device

### ios

1. activate dev mode on device
2. connect device via usb
3. discover device by running `flutter devices` in terminal
4. run `flutter run -d <device id>` in terminal
