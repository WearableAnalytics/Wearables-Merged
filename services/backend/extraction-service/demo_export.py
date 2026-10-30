"""Local-only synthetic export demo: python demo_export.py (requires dev dependencies)."""

from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient

from src.app.main import app, get_db_lord_api
from src.app.schemas import TelemetryPoint


class DemoBackend:
    def __init__(self):
        self.points = []
        for patient, values in [("DEMO-PERSON-A", [72, 75, 70]), ("DEMO-PERSON-B", [81, 79, 83])]:
            for minute, value in enumerate(values):
                self.points.append(
                    TelemetryPoint(
                        measurement="heart-rate",
                        timestamp=datetime(2026, 10, 28, 10, tzinfo=UTC) - timedelta(minutes=minute),
                        tags={"device-id": patient, "category": "measurements.instantaneous", "host": "demo-host"},
                        fields={"value": value, "t_ingested": 1, "note": "Artificial demo data"},
                    )
                )
        duplicate = self.points[0].model_copy(deep=True)
        duplicate.tags["host"] = "other-demo-host"
        duplicate.fields["t_ingested"] = 2
        self.points.append(duplicate)
        for measurement, value in [("demo-unsupported", 42), ("heart-rate", "not a numeric value")]:
            self.points.append(
                TelemetryPoint(
                    measurement=measurement,
                    timestamp=datetime(2026, 10, 28, 9, tzinfo=UTC),
                    tags={"device-id": "DEMO-PERSON-A"},
                    fields={"value": value},
                )
            )

    async def stream_telemetry(self, *, measurement, start, end=None, tags=None):
        for point in sorted(self.points, key=lambda point: point.timestamp, reverse=True):
            if (
                (measurement is None or point.measurement == measurement)
                and point.timestamp >= start
                and (end is None or point.timestamp < end)
                and all(point.tags.get(key) == value for key, value in (tags or {}).items())
            ):
                yield point

    async def list_measurements(self):
        return [{"measurement": "heart-rate", "fieldKeys": ["value", "t_ingested", "note"]}]


PAGE = """<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wearables · Export-Demo</title><style>
body{font:17px/1.6 system-ui;background:#f2f5f8;color:#183042;max-width:1050px;margin:50px auto;padding:24px}
h1{font-size:34px} .badge{color:#14745b;font-weight:700} .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
section{background:white;padding:24px;border-radius:14px;box-shadow:0 3px 15px #18304210}
a,button{display:inline-block;background:#126a87;color:white;border:0;border-radius:7px;padding:10px 16px;margin:6px 6px 6px 0;text-decoration:none;cursor:pointer;font:inherit}
pre{font:13px/1.5 monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#edf3f7;padding:16px;max-height:360px;overflow:auto}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style><p class="badge">LOKALE DEMO · NUR KÜNSTLICHE DATEN</p>
<h1>Export-Pseudonymisierung ausprobieren</h1>
<p>Zwei erfundene Personen, je drei Pulswerte. Eine zusätzliche Kopie wird entfernt.
Zwei weitere Beispiele zeigen ausgelassene Daten: eine unbekannte Messart und ein Textwert.</p>
<div class="grid"><section><h2>Normaler Export</h2>
<p>Enthält die Demo-Patientenkennungen und Zusatzfelder.</p>
<a href="/v1/measurements/export.csv">CSV herunterladen</a>
<a href="/v1/measurements/export.fhir">FHIR herunterladen</a>
<pre id="normal">Wird geladen …</pre></section>
<section><h2>Pseudonymisierter Export</h2>
<p>Zufällige Kennungen pro Download. Zusatzfelder werden entfernt; Werte und Zeitstempel bleiben erhalten.</p>
<p id="export-summary" role="status" aria-live="polite">Exportumfang wird ermittelt …</p>
<a href="/v1/measurements/export.csv?pseudonymize=true">CSV herunterladen</a>
<a href="/v1/measurements/export.fhir?pseudonymize=true">FHIR herunterladen</a>
<pre id="private">Wird geladen …</pre></section></div>
<button onclick="refresh()">Vorschau neu erzeugen</button>
<p>Jeder Abruf erzeugt neue Ersatzkennungen. Die Kennungen in Vorschau und Download unterscheiden sich daher.
Dies ist Pseudonymisierung, keine vollständige Anonymisierung. Der Modus umfasst bekannte numerische Messarten.</p>
<p><a href="/docs">API-Dokumentation</a></p>
<script>async function refresh(){for(const [id,suffix] of [['normal',''],['private','?pseudonymize=true']]){
try{const r=await fetch('/v1/measurements/export.csv'+suffix);if(!r.ok)throw new Error('HTTP '+r.status);
document.getElementById(id).textContent=await r.text();
if(id==='private'){const h=r.headers;
document.getElementById('export-summary').textContent=
h.get('x-export-exported')+' von '+h.get('x-export-considered')+' Messwerten exportiert. '+
h.get('x-export-omitted')+' ausgelassen: '+h.get('x-export-omitted-unsupported')+
' unbekannte Messart(en), '+h.get('x-export-omitted-invalid-value')+
' ungültige Zahlenwerte. Doppelte Kopien zählen nicht als Auslassung.'}}
catch(e){document.getElementById(id).textContent='Fehler: '+e.message;
if(id==='private')document.getElementById('export-summary').textContent='Exportumfang konnte nicht ermittelt werden.'}}}refresh()</script></html>"""


def main():
    backend = DemoBackend()
    app.dependency_overrides[get_db_lord_api] = lambda: backend
    with TestClient(app) as client:

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    body = PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                else:
                    response = client.get(self.path)
                    body = response.content
                    self.send_response(response.status_code)
                    for header in (
                        "content-type",
                        "content-disposition",
                        "x-export-considered",
                        "x-export-exported",
                        "x-export-omitted",
                        "x-export-omitted-unsupported",
                        "x-export-omitted-invalid-value",
                    ):
                        if header in response.headers:
                            self.send_header(header, response.headers[header])
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 8010), Handler)
        print("Synthetic demo: http://127.0.0.1:8010", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            app.dependency_overrides.clear()


if __name__ == "__main__":
    main()
