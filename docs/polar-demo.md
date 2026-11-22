# Polar 360 study demo

The participant links the Wearables app to a local test case on an iPhone or Android phone. **Polar device** on the linked home screen offers automatic band sync, a manual live capture, and an optional Flow import.

| Path | What the participant does | What the study receives |
| --- | --- | --- |
| Automatic Bluetooth sync | Scan, choose **Auto sync** on the band, select the metrics and approve the study destination once. | New device-recorded heart rate, pulse intervals and skin temperature from enrollment onward. The band retains readings between connections. |
| Manual live Bluetooth capture | Choose heart rate, skin temperature or pulse interval. Scan, select the worn band, record with the app open, then review and share or discard. | A short session collects ten readings of one metric. A longer session allows up to 300. Heart rate uses the Bluetooth Heart Rate Service. The other two use Polar Measurement Data, subject to the device's advertised capabilities. The phone shows a receipt and checks storage. Unsent readings live only on the recording screen. |
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
3. In `services/mobile/mobile_app`, use Flutter 3.47.9, run `flutter pub get`, then `flutter run -d <device>` to start the normal application. For iOS, sign with an authorized development team. When the QR has no endpoint override, also pass `--dart-define=INGEST_URL=https://<your-demo-host>/import/ingest` and `--dart-define=CLOUD_CONNECTOR_URL=https://<your-demo-host>/cloud` using the actual demo host. Check the destination shown on the device before sharing.
4. For a live demonstration, record pulse first. Show the phone receipt, then check storage status and the linked participant’s heart-rate chart. For broader coverage, wear the device overnight, sync to Flow, then preview that recording day using the timezone where it was recorded.
5. Each history session expires after 15 minutes. End Session releases it immediately. The connector discards the Polar access token after preview and never persists the refresh token. Preview counts are grouped by metric. Sharing uses the current study bearer token and verifies every importer receipt against byte hash and reading count. A retry during the session resumes at the first unconfirmed batch. An expired session requires fresh authorization. For a Helm-based installation, enable `polar.enabled`, set `polar.redirectUri` and `polar.ingestUrl`, and provide both client credentials in `polar.secretName`. Use a single process for the interactive import; multi-replica durable OAuth sessions and background cloud synchronization need a separate design. Disable access logging of callback query strings at the demo gateway and connector (uvicorn `--no-access-log`).

## Physical demonstration

1. Link the app to a synthetic study case. On the home screen open **Polar device**, scan and select the band you are wearing. Choose a metric and verify that readings arrive. Skin temperature uses °C. A pulse interval is the time between two detected pulse beats, in milliseconds.
2. Review the captured values and destination. Tap **Share** once, record the receipt ID, then use **Check storage status** until the confirmed count equals the number of readings. If acceptance is temporarily unavailable, leave this screen open to retry the same recording.
3. In the dashboard, open the same participant and recording time. Check that the points fall in the recording window and compare the values and units with the reviewed capture. Record the platform, model, firmware and counts for the demo report.
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

- The physical Polar 360 completed first-time setup in Polar Flow, paired to an iPhone 16 Pro Max and ran firmware 6.2.101. The iPhone captured ten live Bluetooth heart-rate readings while the band was worn. All ten reached the local InfluxDB through the importer and FHIR pipeline. The receipt and independent storage query agreed.
- The signed app running its regular Home screen retained the receipt and its ten confirmed readings after relaunch. On the phone open **Home → Upload history**. It displays the last saved confirmation offline. Refreshing status and sharing new readings require a valid study link and connectivity.
- In the normal Wearables web application open the authorized case and select **General data**. Its existing Grafana dashboard shows the heart-rate chart. **Stored readings** shows individual timestamps, values, units and sources. The hardware check used a private local case. For presentations, use a separate case with readings approved for display, or label a synthetic dataset explicitly.
- To revisit a short capture, bookmark `/cases/<case-id>?from=<epoch-ms>&to=<epoch-ms>` with the recording interval. The page expands the range to whole minutes. The uploaded points remain available after removing the band, subject to the InfluxDB retention policy. Keep the local Docker data volumes and run the stack to serve the dashboard.
- The mobile suite passed 48 tests and the connector suite passed nine. A real Android phone and a Polar-authorized history import are still outstanding. The eight history categories above were tested with fixtures. The ten physical readings establish the Bluetooth heart-rate path on iOS.

### Direct Bluetooth sensor verification, 2026-11-22

The same Polar 360 and iPhone sent two additional recordings through the regular Wearables app. The importer accepted each upload. The phone received storage confirmation for all ten skin temperature readings and all ten pulse intervals. Independent InfluxDB queries found ten distinct records for each metric. The case dashboard displayed both series under **General data** in the capture time window.

The initial band setup used Polar Flow. The subsequent Bluetooth measurements required the linked study app, Bluetooth permission, and a reachable study backend for sharing. They used neither Apple Health nor a Polar cloud session. Removing the band after confirmed upload leaves the stored measurements available for the configured retention period. This manual live mode excludes direct raw accelerometry and optical waveforms. The separate automatic path reads band history. The new streams have been tested on physical iOS hardware. Physical Android verification remains open. The mobile suite passed 50 tests, Dart analysis passed for the changed recording code, and both Grafana regression tests passed against the local test stack.

### Automatic daily use

The participant opens **Polar device → Scan for Polar → Auto sync**, reviews the band, destination and categories, then enables sharing. **Turn off** stops future uploads. A changed study credential requires fresh opt-in. Users can revisit accepted batches under **Upload history** and refresh the storage status. Polar Flow, AccessLink and the phone health store are independent sources; the direct sync uses only Bluetooth and the enrolled HTTPS endpoint.

The band records at its own cadence. Wearables reads the 360's stored automatic samples and daily skin-temperature files over read-only Polar file transfer on app launch/resume, every five minutes while the app is active, and when the OS schedules the existing background fetch. The OS controls background opportunities. An unreachable phone or backend delays uploads until a later connection. Force-quitting the app can require reopening it. Catch-up is limited by what the device retains. Sharing never erases data from the band. Configure the band clock to match the phone at enrollment; after a time-zone change the app requests a new opt-in to avoid reinterpreting wall-clock timestamps.

Each outgoing batch is bounded, repeatable and scoped to the enrolled destination. The app checks the active grant again before sending and retrying. Confirmed file prefixes let appends resume without resending older points; changed inputs go through the importer's record identity checks. Consent and checkpoint storage contains no raw measurement payloads. A server receipt confirms acceptance, and the separate storage check confirms downstream delivery.

On a physical Polar 360 and iPhone, nine automatic uploads after opt-in produced 807 distinct records with downstream storage confirmation. The local dashboard's InfluxDB source contained four heart-rate readings, 799 pulse intervals and four skin-temperature readings for that participant and window. To test catch-up, we suspended the iPhone app for 56 seconds while the band continued recording. Nine readings with timestamps inside that interval first reached the importer after the app resumed. All nine received storage confirmation without manual sharing.

The Flutter suite passed 56 tests, and the Android arm64 debug APK built from the same source. A physical Android test, a walk out of Bluetooth range and a multi-day test of OS-scheduled background execution remain open.
