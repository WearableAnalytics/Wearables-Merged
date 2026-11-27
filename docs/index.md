---
hide:
  - toc
---

# Wearables Documentation

Welcome to the documentation portal for the **Wearables** platform (Charité Berlin).

!!! info "Work in Progress"
    This documentation portal is currently starting with the **[Cloud Connector Service](services/cloud-connector/index.md)**. Additional services can be added step by step under [Services](services/index.md).

## Platform Architecture & Data Flow

<div class="arch-widget" data-wearables-arch>
  <div class="arch-toolbar">
    <span class="arch-toolbar-label">Highlight flow:</span>
    <button type="button" class="arch-filter-btn is-active" data-flow="all">All</button>
    <button type="button" class="arch-filter-btn" data-flow="mobile">Mobile Ingest</button>
    <button type="button" class="arch-filter-btn" data-flow="cloud">Cloud Connector</button>
    <button type="button" class="arch-filter-btn" data-flow="ml">ML Pipeline</button>
    <button type="button" class="arch-filter-btn" data-flow="web">Web &amp; Research</button>
    <button type="button" class="arch-expand-btn" data-arch-fullscreen aria-label="Toggle fullscreen diagram">⤢ Fullscreen</button>
  </div>

  <div class="arch-canvas-wrap">
    <svg class="arch-svg" viewBox="0 0 1528 312" role="img" aria-label="Wearables platform end-to-end architecture and data flow">
      <defs>
        <marker id="arch-arrow" viewBox="0 0 10 10" refX="0.5" refY="5" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto">
          <path d="M 0 1.5 L 8.5 5 L 0 8.5 z" fill="context-stroke" />
        </marker>
      </defs>

      <!-- Subtle column zone headers -->
      <text class="arch-zone-title" x="12" y="16">Sources</text>
      <text class="arch-zone-title" x="198" y="16">Ingestion</text>
      <text class="arch-zone-title" x="392" y="16">Kafka &amp; Mapping</text>
      <text class="arch-zone-title" x="598" y="16">Consumers &amp; ML</text>
      <text class="arch-zone-title" x="788" y="16">Storage</text>
      <text class="arch-zone-title" x="992" y="16">Access &amp; Viz</text>
      <text class="arch-zone-title" x="1180" y="16">APIs &amp; Proxy</text>
      <text class="arch-zone-title" x="1374" y="16">End Users</text>

      <!-- ==================== EDGES (stop 7px before target for exact arrowhead tip) ==================== -->
      <!-- Col 1 -> Col 2 -->
      <g class="arch-edge" data-edge="mobile->importservice" data-from="mobile" data-to="importservice">
        <path d="M 158 67 H 191" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge arch-edge-dashed" data-edge="mobile->cloudconnector" data-from="mobile" data-to="cloudconnector">
        <path d="M 85 100 V 138 H 176 V 194 H 191" marker-end="url(#arch-arrow)" />
        <rect class="edge-label-bg" x="96" y="129" width="70" height="16" rx="4" />
        <text class="edge-label" x="131" y="140" text-anchor="middle">OAuth/Sync</text>
      </g>
      <g class="arch-edge" data-edge="providers->cloudconnector" data-from="providers" data-to="cloudconnector">
        <path d="M 158 209 H 191" marker-end="url(#arch-arrow)" />
      </g>

      <!-- Col 2 -> Col 3 & Postgres Archive -->
      <g class="arch-edge" data-edge="importservice->kafka-raw" data-from="importservice" data-to="kafka-raw">
        <path d="M 348 56 H 370 V 44 H 385" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge arch-edge-dashed" data-edge="importservice->postgres" data-from="importservice" data-to="postgres">
        <path d="M 348 82 H 362 V 292 H 868 V 267" marker-end="url(#arch-arrow)" />
        <rect class="edge-label-bg" x="560" y="283" width="106" height="16" rx="4" />
        <text class="edge-label" x="613" y="295" text-anchor="middle">encrypted archive</text>
      </g>
      <g class="arch-edge" data-edge="cloudconnector->kafka-raw" data-from="cloudconnector" data-to="kafka-raw">
        <path d="M 348 209 H 376 V 60 H 385" marker-end="url(#arch-arrow)" />
      </g>

      <!-- Col 3 vertical chain -->
      <g class="arch-edge" data-edge="kafka-raw->mapper" data-from="kafka-raw" data-to="mapper">
        <path d="M 474 76 V 107" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="mapper->kafka-lp" data-from="mapper" data-to="kafka-lp">
        <path d="M 474 172 V 203" marker-end="url(#arch-arrow)" />
      </g>

      <!-- Col 3 -> Col 4 -->
      <g class="arch-edge" data-edge="kafka-lp->telegraf" data-from="kafka-lp" data-to="telegraf">
        <path d="M 556 226 H 577 V 76 H 591" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="kafka-lp->ml" data-from="kafka-lp" data-to="ml">
        <path d="M 556 238 H 591" marker-end="url(#arch-arrow)" />
      </g>

      <!-- Col 4 -> Col 5 -->
      <g class="arch-edge" data-edge="telegraf->influxdb" data-from="telegraf" data-to="influxdb">
        <path d="M 744 76 H 781" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="ml->influxdb" data-from="ml" data-to="influxdb">
        <path d="M 744 226 H 766 V 96 H 781" marker-end="url(#arch-arrow)" />
      </g>

      <!-- Col 5 (Storage) -> Col 6 (Access & Viz) — SHORT DIRECT ARROWS! -->
      <g class="arch-edge" data-edge="influxdb->grafana" data-from="influxdb" data-to="grafana">
        <path d="M 948 72 H 985" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="influxdb->dblord" data-from="influxdb" data-to="dblord">
        <path d="M 948 94 H 970 V 198 H 985" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="postgres->dblord" data-from="postgres" data-to="dblord">
        <path d="M 948 227 H 985" marker-end="url(#arch-arrow)" />
      </g>

      <!-- Col 6 -> Col 7 -->
      <g class="arch-edge" data-edge="grafana->grafanaproxy" data-from="grafana" data-to="grafanaproxy">
        <path d="M 1136 61 H 1173" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="dblord->bff" data-from="dblord" data-to="bff">
        <path d="M 1136 198 H 1158 V 156 H 1173" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="dblord->extraction" data-from="dblord" data-to="extraction">
        <path d="M 1136 222 H 1158 V 251 H 1173" marker-end="url(#arch-arrow)" />
      </g>

      <!-- Col 7 inter-service dashed links -->
      <g class="arch-edge arch-edge-dashed" data-edge="bff->grafanaproxy" data-from="bff" data-to="grafanaproxy">
        <path d="M 1255 124 V 97" marker-end="url(#arch-arrow)" />
        <rect class="edge-label-bg" x="1262" y="99" width="48" height="15" rx="4" />
        <text class="edge-label" x="1286" y="110" text-anchor="middle">/api/me</text>
      </g>
      <g class="arch-edge arch-edge-dashed" data-edge="extraction->bff" data-from="extraction" data-to="bff">
        <path d="M 1255 222 V 195" marker-end="url(#arch-arrow)" />
        <rect class="edge-label-bg" x="1262" y="198" width="80" height="15" rx="4" />
        <text class="edge-label" x="1302" y="209" text-anchor="middle">/api/extraction</text>
      </g>

      <!-- Col 7 -> Col 8 -->
      <g class="arch-edge" data-edge="grafanaproxy->web" data-from="grafanaproxy" data-to="web">
        <path d="M 1330 61 H 1352 V 88 H 1367" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="bff->web" data-from="bff" data-to="web">
        <path d="M 1330 156 H 1352 V 120 H 1367" marker-end="url(#arch-arrow)" />
      </g>
      <g class="arch-edge" data-edge="extraction->researchers" data-from="extraction" data-to="researchers">
        <path d="M 1330 251 H 1367" marker-end="url(#arch-arrow)" />
      </g>

      <!-- ==================== NODES ==================== -->
      <!-- Col 1: Sources -->
      <g class="arch-node" data-node="mobile">
        <rect class="node-box" x="12" y="34" width="146" height="66" rx="9" />
        <text class="node-title" x="24" y="60">Mobile App</text>
        <text class="node-sub" x="24" y="80">HealthKit/Connect</text>
      </g>

      <g class="arch-node" data-node="providers">
        <rect class="node-box" x="12" y="176" width="146" height="66" rx="9" />
        <text class="node-title" x="24" y="202">Cloud Providers</text>
        <text class="node-sub" x="24" y="222">Garmin, Polar, Oura...</text>
      </g>

      <!-- Col 2: Ingestion -->
      <g class="arch-node" data-node="importservice">
        <rect class="node-box" x="198" y="34" width="150" height="66" rx="9" />
        <text class="node-title" x="210" y="60">Import Service</text>
        <text class="node-sub" x="210" y="80">Upload gateway</text>
      </g>

      <g class="arch-node" data-node="cloudconnector">
        <rect class="node-box" x="198" y="176" width="150" height="66" rx="9" />
        <circle class="node-doc-dot" cx="336" cy="189" r="3.5" />
        <text class="node-title" x="210" y="202">Cloud Connector</text>
        <text class="node-sub" x="210" y="222">OAuth &amp; Webhooks</text>
      </g>

      <!-- Col 3: Kafka & Mapping -->
      <g class="arch-node" data-node="kafka-raw">
        <rect class="node-box" x="392" y="24" width="164" height="52" rx="9" />
        <text class="node-title" x="404" y="46">Kafka: wearables-raw</text>
        <text class="node-sub" x="404" y="64">Raw ingest topic</text>
      </g>

      <g class="arch-node" data-node="mapper">
        <rect class="node-box" x="392" y="114" width="164" height="58" rx="9" />
        <text class="node-title" x="404" y="138">FHIR Mapper</text>
        <text class="node-sub" x="404" y="157">+ Validator (Java)</text>
      </g>

      <g class="arch-node" data-node="kafka-lp">
        <rect class="node-box" x="392" y="210" width="164" height="52" rx="9" />
        <text class="node-title" x="404" y="232">Kafka: wearables-lp</text>
        <text class="node-sub" x="404" y="250">Line-protocol topic</text>
      </g>

      <!-- Col 4: Consumers & ML -->
      <g class="arch-node" data-node="telegraf">
        <rect class="node-box" x="598" y="46" width="146" height="60" rx="9" />
        <text class="node-title" x="610" y="71">Telegraf</text>
        <text class="node-sub" x="610" y="90">Kafka consumer</text>
      </g>

      <g class="arch-node" data-node="ml">
        <rect class="node-box" x="598" y="198" width="146" height="64" rx="9" />
        <text class="node-title" x="610" y="224">ML Pipeline</text>
        <text class="node-sub" x="610" y="244">Spark, Feast, MLflow</text>
      </g>

      <!-- Col 5: Storage -->
      <g class="arch-node arch-node-db" data-node="influxdb">
        <rect class="node-box" x="788" y="38" width="160" height="82" rx="9" />
        <text class="node-title" x="800" y="61">InfluxDB</text>
        <text class="node-sub" x="800" y="79">Time-series buckets</text>
        <rect class="node-pill-bg" x="800" y="90" width="96" height="18" rx="9" />
        <text class="node-pill-text" x="848" y="103" text-anchor="middle">will be replaced</text>
      </g>

      <g class="arch-node arch-node-db" data-node="postgres">
        <rect class="node-box" x="788" y="194" width="160" height="66" rx="9" />
        <text class="node-title" x="800" y="220">PostgreSQL</text>
        <text class="node-sub" x="800" y="240">Accounts &amp; archive</text>
      </g>

      <!-- Col 6: Access & Viz -->
      <g class="arch-node" data-node="grafana">
        <rect class="node-box" x="992" y="40" width="144" height="64" rx="9" />
        <text class="node-title" x="1004" y="66">Grafana</text>
        <text class="node-sub" x="1004" y="86">Dashboards</text>
      </g>

      <g class="arch-node" data-node="dblord">
        <rect class="node-box" x="992" y="176" width="144" height="68" rx="9" />
        <text class="node-title" x="1004" y="204">db_lord</text>
        <text class="node-sub" x="1004" y="224">Storage API</text>
      </g>

      <!-- Col 7: APIs & Proxy -->
      <g class="arch-node" data-node="grafanaproxy">
        <rect class="node-box" x="1180" y="32" width="150" height="58" rx="9" />
        <text class="node-title" x="1192" y="56">Grafana Proxy</text>
        <text class="node-sub" x="1192" y="74">JWT embed proxy</text>
      </g>

      <g class="arch-node" data-node="bff">
        <rect class="node-box" x="1180" y="124" width="150" height="64" rx="9" />
        <text class="node-title" x="1192" y="150">Wearables BFF</text>
        <text class="node-sub" x="1192" y="170">Auth, cases &amp; /api</text>
      </g>

      <g class="arch-node" data-node="extraction">
        <rect class="node-box" x="1180" y="222" width="150" height="58" rx="9" />
        <text class="node-title" x="1192" y="246">Extraction Service</text>
        <text class="node-sub" x="1192" y="264">JSON/CSV export</text>
      </g>

      <!-- Col 8: End Users -->
      <g class="arch-node" data-node="web">
        <rect class="node-box" x="1374" y="66" width="142" height="76" rx="9" />
        <text class="node-title" x="1386" y="98">Web Frontend</text>
        <text class="node-sub" x="1386" y="118">React + Vite UI</text>
      </g>

      <g class="arch-node" data-node="researchers">
        <rect class="node-box" x="1374" y="222" width="142" height="58" rx="9" />
        <text class="node-title" x="1386" y="246">Researchers</text>
        <text class="node-sub" x="1386" y="264">Dataset exports</text>
      </g>
    </svg>
  </div>

  <div class="arch-inspector" aria-live="polite"></div>
</div>

## Quick Navigation

- **[Services](services/index.md)**
  - [Cloud Connector](services/cloud-connector/index.md): OAuth 2.0 PKCE linking, provider webhooks, REST sync and provider limits
