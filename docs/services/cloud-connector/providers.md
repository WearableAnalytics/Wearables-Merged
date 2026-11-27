# Providers & Limits

Registered in `services/backend/cloud-connector/app/providers/__init__.py`.

## Implemented Providers

| Provider Key | Ecosystem | Auth Flow | Sync & Webhooks |
|---|---|---|---|
| `garmin` | [Garmin Connect](https://developer.garmin.com/gc-developer-program/overview/) | OAuth 2.0 PKCE | PUSH webhooks (primary) + REST backfill or `mock_data` (HR, HRV, sleep, SpO2, stress, ECG, activities) |
| `polar` | [Polar AccessLink v3](https://www.polar.com/accesslink-api/#polar-accesslink-api) | OAuth 2.0 + user registration | REST sync (sleep, continuous HR, exercises; webhooks currently logged only) |
| `google_health` | [Google Health](https://developers.google.com/health) (Fitbit, Pixel Watch & Health Connect) | OAuth 2.0 PKCE | REST sync (sleep stages, 24/7 & resting HR, activities, SpO2, respiration; Pub/Sub pings currently logged only) |
| `oura` | [Oura Ring Cloud v2](https://cloud.ouraring.com/v2/docs/) | OAuth 2.0 PKCE | REST sync (sleep stages, readiness, resting HR, HRV, continuous HR, workouts, SpO2; webhooks currently logged only) |
| `whoop` | [WHOOP v2](https://developer.whoop.com/api) | OAuth 2.0 PKCE | REST sync (recovery, HRV, skin temp, sleep stages, workouts, cycles) + v2 webhook parsing |
| `withings` | [Withings Health](https://developer.withings.com/) | OAuth 2.0 PKCE | REST sync (body weight, body fat, blood pressure, resting HR, SpO2, temperature, sleep, workouts; webhooks currently logged only) |

Credentials use `<PROVIDER>_CLIENT_ID` and `<PROVIDER>_CLIENT_SECRET`.

## Provider Limits & Production Requirements

Most provider APIs have rate limits alongside different testing limits and production approvals (links go to the respective provider, limit or verification docs):

| Provider | Scope | Testing Limit | Production Requirement |
|---|---|---|---|
| [Garmin](https://developer.garmin.com/gc-developer-program/overview/) | Garmin Devices (+ Activities & Sleep) | 1000 Users | Approval and/or Contract |
| [Polar](https://www.polar.com/accesslink-api/#security) | Watches & Straps | No User Limit | No User Limit (Rate-limited) |
| [Google Health](https://support.google.com/cloud/answer/10311615#zippy=%2Ctesting) | Fitbit, Pixel (+ Health Connect) | 100 Users | Unlimited (App Verification & Security) |
| [Oura](https://cloud.ouraring.com/v2/docs#section/Getting-Started/Common-Questions) | Oura Ring | 10 Users | Unlimited (Approval) |
| [Whoop](https://developer.whoop.com/docs/developing/rate-limiting) | Whoop Strap | 10 Users | Tiered up to Unlimited |
| [Withings](https://developer.withings.com/developer-guide/v3/withings-solutions/withings-api-plans) | Scales, Blood Pressure, Watches | Sandbox Limit *(check Withings console)* | Unlimited (Review) |
