# Polar 360 study demo

The participant links the Wearables app to a local test case on an iPhone or Android phone. **Polar device** on the linked home screen offers two independent paths.

| Path | What the participant does | What the study receives |
| --- | --- | --- |
| Bluetooth Heart Rate Service | Wear the Polar, enable HR broadcasting if required by the model, scan, select the device and record. Review and share, or discard. | Up to ten pulse readings in a foreground recording. The phone timestamps each notification. The screen shows live bpm, then an archive receipt and a storage-status check. Unsent recordings live only on this screen. |
| Polar Flow / AccessLink v4 | Sync the device in Polar Flow. Choose **Import a day from Polar Flow**, the recording date, time zone and categories. Authorize in Polar’s browser page, return to Wearables, preview counts and tap Share. | Supported observations from that Flow account for the selected day, including device identifiers where Polar supplies them. Cloud timing depends on the last device-to-Flow sync. |
| Phone health store | In Polar Flow, enable Apple Health or Health Connect. Allow the categories wanted in both apps and use the existing Wearables health-store sync. | The intersection of what Flow exports and what the existing platform importer supports. Flow exports workout HR through both bridges. Avoid overlapping recording paths when comparing counts. |

## AccessLink categories

| Selection | Measurements in this implementation |
| --- | --- |
| Continuous pulse | Heart rate |
| Activity | Step counts and metabolic-equivalent samples over Polar’s intervals |
| Training | Elapsed time, total distance and workout energy |
| Sleep | Awake, light (N1/N2), deep (N3), REM, Polar overall sleep score |
| Recovery | Breathing-rate samples and nightly mean RMSSD. The RMSSD summary uses the result creation time. Polar does not identify a measuring device on this response. |
| Temperature | Skin temperature in °C |
| Pulse intervals | Optical PPI and its error estimate in ms for samples reporting skin contact and no movement |
| Skin contact | Contact state changes, encoded as 1 or 0 |

Device firmware, Flow configuration, API entitlement and having recorded a qualifying session affect availability. A day without sleep or training data may yield empty categories. Raw accelerometer/optical waveforms, ECG, GPS routes, and backfilling every Polar metric are outside this implementation. BLE and Flow records have different identities. Replaying an individual source reading is supported; matching the same physiological event across sources is separate work.

## Local setup

1. Follow the [local Compose setup](../deploy/local/README.md) to start the Wearables local ingestion stack with the branch’s mapper configuration. Use a local test enrollment token. On a physical phone, use a reachable HTTPS gateway with a trusted certificate. Point the enrollment at the local importer and connector (e.g. paths `/import/ingest` and `/cloud`). The app displays the destination host before sharing. Verify it before sending real data.
2. For Bluetooth only, no Polar cloud credentials are needed. For history, register an AccessLink client with an exact callback URL that the phone browser can reach, e.g. `https://<your-demo-host>/cloud/polar/callback`. Configure a single local cloud-connector process with the existing study JWT settings and the following environment variables. With local Compose, supply the three Polar client settings through the local environment and recreate the cloud-connector service. Compose supplies the internal importer URL and disables connector access logs. Keep secrets outside the repository.
   - `POLAR_CLIENT_ID` and `POLAR_CLIENT_SECRET` from the registered Polar client
   - `POLAR_REDIRECT_URI` matching the registered callback
   - `POLAR_INGEST_URL` pointing from the connector to the local importer’s `/ingest`
3. In `services/mobile/mobile_app`, use Flutter 3.47.9, run `flutter pub get`, then `flutter run -d <device> --dart-define=POLAR_FLOW_ENABLED=true`. For iOS, sign with an authorized development team. A debug study QR with a cloud endpoint also enables the history entry. When the QR has no endpoint override, also pass `--dart-define=INGEST_URL=https://<your-demo-host>/import/ingest` and `--dart-define=CLOUD_CONNECTOR_URL=https://<your-demo-host>/cloud` using the actual demo host. The feature flag alone leaves the project’s default destinations in place.
4. For a live demonstration, record pulse first. Show the phone receipt, then check storage status and the linked participant’s heart-rate chart. For broader coverage, wear the device overnight, sync to Flow, then preview that recording day using the timezone where it was recorded.
5. Each history session expires after 15 minutes. End Session releases it immediately. The connector discards the Polar access token after preview and never persists the refresh token. Preview counts are grouped by metric. Sharing uses the current study bearer token and verifies every importer receipt against byte hash and reading count. A retry during the session resumes at the first unconfirmed batch. An expired session requires fresh authorization. Use a single local process for this demo; multi-replica durable OAuth sessions and background cloud synchronization need a separate design. Disable access logging of callback query strings at the demo gateway and connector (uvicorn `--no-access-log`).

## Physical demonstration

1. Link the app to a synthetic study case. On the home screen open **Polar device**, scan and select the band you are wearing. Verify that the displayed bpm changes as notifications arrive.
2. Review the captured values and destination. Tap **Share** once, record the receipt ID, then use **Check storage status** until the confirmed count equals the number of readings. If acceptance is temporarily unavailable, leave this screen open to retry the same recording.
3. In the dashboard, open the same participant and recording time. Check that the points fall in the recording window and compare the bpm values with the reviewed capture. Record the platform, model, firmware and counts for the demo report.
4. For history, sync to Flow first. Select a date with known data and start with one category (e.g. sleep after an overnight recording). Compare the preview and stored values with Flow. Additional categories with no observations for that day can validly return zero.

## Verification

Run `flutter test` in the mobile app, `pytest -q` in the cloud connector, `mvn test` in the mapper and `python3 scripts/sync-measurement-mapping.py --check` at the repository root. The connector tests simulate Polar, check all eight category shapes, case isolation, one-use OAuth state, review before upload and idempotent resubmission. Hardware sign-off requires a physical BLE connection, the actual Polar consent flow, and checking real stored results against the source values on both platforms.

### Local verification record, 2026-11-21

- The mobile suite passed 46 tests, including Bluetooth packet parsing, upload identity on both platform paths, and the category selection required before authorization. The new Dart files passed static analysis.
- The connector suite passed 9 tests. The mapper passed 23 tests, including validation of each declared measurement with its canonical unit. The three local stack configuration tests also passed.
- Three connected tests ran against isolated PostgreSQL, Kafka, the Java FHIR mapper, Telegraf and InfluxDB. Synthetic Bluetooth input for each phone platform and a synthetic Flow day containing all 17 measurement types reached storage. Replaying the same upload reused its receipt.
- The iOS debug build compiled for a device without code signing. The Android arm64 debug APK also built with Flutter 3.47.9. Pairing, physiological values, Polar authorization with a registered client and a real Android phone remain hardware/demo checks.

Polar publishes the device services in the [360 manual](https://support.polar.com/e_manuals/polar-360/polar-360-user-manual-english/manual.pdf) and the cloud schemas and scopes in the [AccessLink v4 reference](https://www.polar.com/polar-api-v4/).

### Physical iPhone check, 2026-11-22

- A locally signed build ran on an iPhone 16 Pro Max. Enabling new Bluetooth connections in iOS allowed discovery. The phone saw a connectable, unnamed advertisement with Polar’s manufacturer identifier. The advertisement alone did not identify the model.
- The app and a separate native CoreBluetooth check both timed out while connecting. The recording contained zero heart-rate samples, and the local importer had accepted zero uploads. Physical pairing, pulse capture and downstream confirmation remain open.
- The mobile suite passed 47 tests after adding Bluetooth availability checks and discovery by Polar manufacturer identifier. For an unconfigured band, follow [Polar’s first-time setup instructions](https://support.polar.com/e_manuals/polar-360/polar-360-flow-user-manual-english/setting-up-polar-360.htm) before repeating the hardware check.
- After a physical reset, Polar Flow identified the loan band explicitly as a Polar 360. iOS accepted its Bluetooth pairing request and Flow reached the device settings and first sync. The earlier unnamed advertisement alone was insufficient to establish model identity. This verifies the phone-to-band pairing step independently of pulse capture in Wearables.
- Flow installed the offered 6.2.101 firmware update and displayed “Setup completed”. In the local Wearables build, a fresh scan listed the named Polar 360 and selecting it reached the heart-rate notification step. Only a nonzero sample count establishes pulse capture.
