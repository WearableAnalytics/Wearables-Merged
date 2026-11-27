/* Interactive Architecture */
(function () {
  const NODES = {
    mobile: {
      title: "Mobile App",
      subtitle: "Flutter · iOS HealthKit & Android Health Connect",
      path: "services/mobile/mobile_app",
      inputs: "Apple HealthKit, Android Health Connect, Study QR Code",
      outputs: "Import Service (health uploads), Cloud Connector (OAuth/Sync)",
      description:
        "Collects wearable data on iOS and Android and lets participants link external cloud providers.",
    },
    providers: {
      title: "Cloud Providers",
      subtitle: "External wearable cloud APIs",
      path: "services/backend/cloud-connector/app/providers",
      inputs: "Wearables & provider accounts",
      outputs: "Cloud Connector (webhooks & REST API)",
      description:
        "External providers connected via OAuth 2.0: Garmin, Polar, Google Health (Fitbit, Pixel Watch & Health Connect), Oura, Whoop and Withings.",
      link: { label: "View Providers & Limits →", href: "services/cloud-connector/providers/" },
    },
    importservice: {
      title: "Import Service",
      subtitle: "FastAPI · Mobile upload gateway",
      path: "services/backend/importservice",
      inputs: "Mobile App (JWT)",
      outputs: "Kafka wearables-raw, PostgreSQL encrypted archive",
      description:
        "Validates JWTs, saves encrypted uploads and delivery receipts in PostgreSQL, forwards data to Kafka.",
    },
    cloudconnector: {
      title: "Cloud Connector",
      subtitle: "FastAPI · OAuth 2.0 PKCE, Webhooks & Sync",
      path: "services/backend/cloud-connector",
      inputs: "Cloud Providers (webhooks/REST), Mobile App (OAuth/Sync)",
      outputs: "Kafka wearables-raw",
      description:
        "Handles provider OAuth linking, token refreshes, PUSH webhooks and REST sync into Kafka.",
      link: { label: "Open Cloud Connector Docs →", href: "services/cloud-connector/" },
    },
    "kafka-raw": {
      title: "Kafka: wearables-raw",
      subtitle: "Raw ingestion topic",
      path: "gitops/apps/platform/kafka",
      inputs: "Import Service, Cloud Connector",
      outputs: "FHIR Mapper + Validator",
      description:
        "Kafka topic carrying raw incoming health data from mobile and cloud ingestion.",
    },
    mapper: {
      title: "FHIR Mapper + Validator",
      subtitle: "Java · Kafka Streams",
      path: "services/backend/fhir-mapper-validator",
      inputs: "Kafka wearables-raw",
      outputs: "Kafka wearables-lp, wearables-ingestion-results, dlq",
      description:
        "Validates and converts incoming records into FHIR and InfluxDB line protocol using the mapping YAML.",
    },
    "kafka-lp": {
      title: "Kafka: wearables-lp",
      subtitle: "Line-protocol topic",
      path: "gitops/apps/platform/kafka",
      inputs: "FHIR Mapper + Validator",
      outputs: "Telegraf, ML Pipeline (Spark Structured Streaming)",
      description:
        "Kafka topic with normalized line-protocol data consumed by Telegraf and the ML pipeline.",
    },
    telegraf: {
      title: "Telegraf",
      subtitle: "Kafka consumer & InfluxDB writer",
      path: "gitops/apps/monitoring/telegraf",
      inputs: "Kafka wearables-lp",
      outputs: "InfluxDB (measurements bucket)",
      description:
        "Reads line-protocol batches from Kafka, enriches device tags via Starlark and writes to InfluxDB.",
    },
    ml: {
      title: "ML Pipeline",
      subtitle: "Spark Streaming · SeaweedFS/LakeFS · Feast · MLflow · KServe",
      path: "gitops/apps/ml-pipeline",
      inputs: "Kafka wearables-lp",
      outputs: "SeaweedFS/LakeFS (Delta Lake), InfluxDB (ml_predictions)",
      description:
        "Reads wearables-lp via Spark Streaming into Delta tables, serves features via Feast, runs MLflow models and writes predictions to InfluxDB.",
    },
    influxdb: {
      title: "InfluxDB",
      badge: "will be replaced",
      subtitle: "Time-series database",
      path: "gitops/apps/monitoring/influxdb",
      inputs: "Telegraf, ML Pipeline",
      outputs: "Grafana, db_lord",
      description:
        "Stores wearable measurements and ML predictions. Planned to be replaced.",
    },
    postgres: {
      title: "PostgreSQL",
      subtitle: "Relational database & upload archive",
      path: "gitops/apps/platform/prod-postgres",
      inputs: "db_lord, Import Service, ML Pipeline",
      outputs: "db_lord",
      description:
        "Stores staff accounts, cases, encrypted upload archives/receipts and MLflow/Feast metadata.",
    },
    dblord: {
      title: "db_lord",
      subtitle: "FastAPI · Storage API (REST & GraphQL)",
      path: "services/backend/db_lord",
      inputs: "InfluxDB, PostgreSQL",
      outputs: "Wearables BFF, Extraction Service",
      description:
        "Database API serving case metadata and time-series queries for Wearables BFF and Extraction Service.",
    },
    grafana: {
      title: "Grafana",
      subtitle: "Dashboards",
      path: "gitops/apps/monitoring/grafana",
      inputs: "InfluxDB/InfluxQL, Prometheus",
      outputs: "Grafana Proxy",
      description:
        "Displays general health, 6-minute walk test, AI Insights and cluster dashboards.",
    },
    extraction: {
      title: "Extraction Service",
      subtitle: "FastAPI · Export API",
      path: "services/backend/extraction-service",
      inputs: "db_lord",
      outputs: "Researchers (JSON/CSV via /api/extraction)",
      description:
        "Exports study datasets as JSON and CSV for researchers behind Wearables BFF (/api/extraction).",
    },
    bff: {
      title: "Wearables BFF",
      subtitle: "Node.js/TypeScript · Main Web API & Auth",
      path: "services/backend/wearables-bff",
      inputs: "db_lord, Extraction Service (/api/extraction)",
      outputs: "Web Frontend (/api), Grafana Proxy (/api/me)",
      description:
        "Manages staff login, study cases, QR JWTs, session checks for Grafana Proxy and /api/extraction routing.",
    },
    grafanaproxy: {
      title: "Grafana Proxy",
      subtitle: "Node.js/TypeScript · Embed proxy",
      path: "services/backend/grafana-proxy",
      inputs: "Grafana, Wearables BFF (/api/me)",
      outputs: "Web Frontend (/proxy/embed)",
      description:
        "Checks active staff authority via Wearables BFF and issues JWT assertions for embedded Grafana views.",
    },
    researchers: {
      title: "Researchers",
      subtitle: "Study data consumers",
      path: "docs/deploy-runtime-config.md",
      inputs: "Extraction Service (/api/extraction)",
      outputs: "Clinical analysis (JSON/CSV)",
      description:
        "Query study measurements programmatically and can use personal export API tokens.",
    },
    web: {
      title: "Web Frontend",
      subtitle: "React + Vite · Staff portal",
      path: "services/web",
      inputs: "Wearables BFF (/api), Grafana Proxy (/proxy)",
      outputs: "Case management, QR onboarding & dashboards",
      description:
        "Web UI to manage cases, generate participant QR codes and view Grafana dashboards.",
    },
  };

  const FLOWS = {
    all: null,
    mobile: {
      nodes: ["mobile", "importservice", "kafka-raw", "mapper", "kafka-lp", "telegraf", "influxdb", "postgres"],
      edges: [
        "mobile->importservice",
        "importservice->kafka-raw",
        "importservice->postgres",
        "kafka-raw->mapper",
        "mapper->kafka-lp",
        "kafka-lp->telegraf",
        "telegraf->influxdb",
      ],
    },
    cloud: {
      nodes: ["mobile", "providers", "cloudconnector", "kafka-raw", "mapper", "kafka-lp", "telegraf", "influxdb"],
      edges: [
        "mobile->cloudconnector",
        "providers->cloudconnector",
        "cloudconnector->kafka-raw",
        "kafka-raw->mapper",
        "mapper->kafka-lp",
        "kafka-lp->telegraf",
        "telegraf->influxdb",
      ],
    },
    ml: {
      nodes: ["kafka-lp", "ml", "influxdb", "grafana", "grafanaproxy", "web"],
      edges: [
        "kafka-lp->ml",
        "ml->influxdb",
        "influxdb->grafana",
        "grafana->grafanaproxy",
        "grafanaproxy->web",
      ],
    },
    web: {
      nodes: ["influxdb", "postgres", "dblord", "bff", "extraction", "grafana", "grafanaproxy", "web", "researchers"],
      edges: [
        "influxdb->dblord",
        "postgres->dblord",
        "influxdb->grafana",
        "dblord->bff",
        "dblord->extraction",
        "extraction->bff",
        "extraction->researchers",
        "grafana->grafanaproxy",
        "bff->grafanaproxy",
        "bff->web",
        "grafanaproxy->web",
      ],
    },
  };

  function initArchitectureDiagram() {
    const root = document.querySelector("[data-wearables-arch]");
    if (!root || root.dataset.archInit === "1") return;
    root.dataset.archInit = "1";

    const svg = root.querySelector("svg.arch-svg");
    const inspector = root.querySelector(".arch-inspector");
    const filterButtons = Array.from(root.querySelectorAll(".arch-filter-btn"));
    const nodeEls = Array.from(svg.querySelectorAll("[data-node]"));
    const edgeEls = Array.from(svg.querySelectorAll("[data-edge]"));

    let activeFlow = "all";
    let selectedNode = null;

    function renderInspector(nodeId) {
      if (!nodeId || !NODES[nodeId]) {
        inspector.classList.add("is-empty");
        inspector.innerHTML =
          '<span class="arch-inspector-hint">Click any component to inspect details, data flow and links.</span>';
        return;
      }

      inspector.classList.remove("is-empty");
      const info = NODES[nodeId];
      const badgeHtml = info.badge
        ? `<span class="arch-inspector-badge">${info.badge}</span>`
        : "";
      const linkHtml = info.link
        ? `<a class="arch-inspector-link" href="${info.link.href}">${info.link.label}</a>`
        : "";

      inspector.innerHTML = `
        <div class="arch-inspector-top">
          <div>
            <div class="arch-inspector-title">${info.title} ${badgeHtml}</div>
            <div class="arch-inspector-sub">${info.subtitle}</div>
          </div>
          <div class="arch-inspector-actions">
            ${linkHtml}
            <button type="button" class="arch-inspector-close" aria-label="Clear selection">Reset</button>
          </div>
        </div>
        <p class="arch-inspector-desc">${info.description}</p>
        <div class="arch-inspector-meta">
          <div><strong>In:</strong> ${info.inputs}</div>
          <div><strong>Out:</strong> ${info.outputs}</div>
          <div><strong>Code:</strong> <code>${info.path}</code></div>
        </div>
      `;

      const closeBtn = inspector.querySelector(".arch-inspector-close");
      if (closeBtn) {
        closeBtn.addEventListener("click", () => {
          selectedNode = null;
          applyHighlight();
        });
      }
    }

    function applyHighlight() {
      filterButtons.forEach((btn) => {
        btn.classList.toggle("is-active", !selectedNode && btn.dataset.flow === activeFlow);
      });

      if (selectedNode) {
        const connectedEdges = new Set();
        const connectedNodes = new Set([selectedNode]);

        edgeEls.forEach((edge) => {
          const from = edge.dataset.from;
          const to = edge.dataset.to;
          if (from === selectedNode || to === selectedNode) {
            connectedEdges.add(edge.dataset.edge);
            connectedNodes.add(from);
            connectedNodes.add(to);
          }
        });

        nodeEls.forEach((el) => {
          const id = el.dataset.node;
          el.classList.toggle("is-selected", id === selectedNode);
          el.classList.toggle("is-dimmed", !connectedNodes.has(id));
        });

        edgeEls.forEach((el) => {
          const isConn = connectedEdges.has(el.dataset.edge);
          el.classList.toggle("is-highlighted", isConn);
          el.classList.toggle("is-dimmed", !isConn);
        });

        renderInspector(selectedNode);
        return;
      }

      const flow = FLOWS[activeFlow];
      if (!flow) {
        nodeEls.forEach((el) => el.classList.remove("is-selected", "is-dimmed"));
        edgeEls.forEach((el) => el.classList.remove("is-highlighted", "is-dimmed"));
      } else {
        const nodeSet = new Set(flow.nodes);
        const edgeSet = new Set(flow.edges);
        nodeEls.forEach((el) => {
          el.classList.remove("is-selected");
          el.classList.toggle("is-dimmed", !nodeSet.has(el.dataset.node));
        });
        edgeEls.forEach((el) => {
          const active = edgeSet.has(el.dataset.edge);
          el.classList.toggle("is-highlighted", active);
          el.classList.toggle("is-dimmed", !active);
        });
      }
      renderInspector(null);
    }

    filterButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedNode = null;
        activeFlow = btn.dataset.flow || "all";
        applyHighlight();
      });
    });

    nodeEls.forEach((el) => {
      el.setAttribute("tabindex", "0");
      el.setAttribute("role", "button");
      const toggle = (ev) => {
        ev.stopPropagation();
        const id = el.dataset.node;
        selectedNode = selectedNode === id ? null : id;
        applyHighlight();
      };
      el.addEventListener("click", toggle);
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          toggle(ev);
        }
      });
    });

    svg.addEventListener("click", () => {
      if (selectedNode) {
        selectedNode = null;
        applyHighlight();
      }
    });

    const fsBtn = root.querySelector("[data-arch-fullscreen]");
    if (fsBtn) {
      const setFullscreen = (open) => {
        root.classList.toggle("is-fullscreen", open);
        document.body.style.overflow = open ? "hidden" : "";
        fsBtn.textContent = open ? "✕ Close" : "⤢ Fullscreen";
      };
      fsBtn.addEventListener("click", () => {
        setFullscreen(!root.classList.contains("is-fullscreen"));
      });
      document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape" && root.classList.contains("is-fullscreen")) {
          setFullscreen(false);
        }
      });
    }

    applyHighlight();
  }

  function initCollapsibleSidebars() {
    const contentInner = document.querySelector(".md-content__inner");
    if (!contentInner) return;

    let reopenBar = contentInner.querySelector(".sidebar-reopen-bar");
    if (!reopenBar) {
      reopenBar = document.createElement("div");
      reopenBar.className = "sidebar-reopen-bar";
      contentInner.insertBefore(reopenBar, contentInner.firstChild);
    }

    /* Left navigation sidebar toggle */
    const primaryNav = document.querySelector(".md-sidebar--primary nav.md-nav--primary");
    const primaryList = primaryNav ? primaryNav.querySelector(":scope > ul.md-nav__list") : null;
    if (primaryNav && primaryList) {
      const NAV_KEY = "wearables-nav-collapsed";

      let navHeader = primaryNav.querySelector(".nav-collapse-header");
      if (!navHeader) {
        navHeader = document.createElement("div");
        navHeader.className = "nav-collapse-header";
        navHeader.innerHTML =
          '<span>Navigation</span><button type="button" class="sidebar-hide-btn nav-hide-btn" title="Hide navigation" aria-label="Hide navigation">&laquo;</button>';
        primaryNav.insertBefore(navHeader, primaryList);
      }

      let navReopen = reopenBar.querySelector(".nav-reopen-btn");
      if (!navReopen) {
        navReopen = document.createElement("button");
        navReopen.type = "button";
        navReopen.className = "sidebar-reopen-btn nav-reopen-btn";
        navReopen.innerHTML = "Navigation &raquo;";
        navReopen.title = "Show navigation";
        reopenBar.insertBefore(navReopen, reopenBar.firstChild);
      }

      const navHide = navHeader.querySelector(".nav-hide-btn");
      const syncNav = (collapsed) => {
        document.body.classList.toggle("nav-collapsed", collapsed);
        navReopen.setAttribute("aria-expanded", String(!collapsed));
      };

      const savedNav = window.localStorage && localStorage.getItem(NAV_KEY) === "1";
      syncNav(savedNav);

      const toggleNav = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const next = !document.body.classList.contains("nav-collapsed");
        syncNav(next);
        try {
          localStorage.setItem(NAV_KEY, next ? "1" : "0");
        } catch (_) {}
      };

      if (!navReopen.dataset.bound) {
        navReopen.dataset.bound = "1";
        navReopen.addEventListener("click", toggleNav);
      }
      if (navHide && !navHide.dataset.bound) {
        navHide.dataset.bound = "1";
        navHide.addEventListener("click", toggleNav);
      }
    }

    /* Right "On this page" sidebar toggle */
    const tocSidebar = document.querySelector(".md-sidebar--secondary");
    if (!tocSidebar || tocSidebar.hasAttribute("hidden")) return;

    const TOC_KEY = "wearables-toc-collapsed";
    const tocTitle = tocSidebar.querySelector("nav.md-nav--secondary > label.md-nav__title");

    let tocReopen = reopenBar.querySelector(".toc-reopen-btn");
    if (!tocReopen) {
      tocReopen = document.createElement("button");
      tocReopen.type = "button";
      tocReopen.className = "sidebar-reopen-btn toc-reopen-btn";
      tocReopen.innerHTML = "&laquo; On this page";
      tocReopen.title = "Show page outline";
      reopenBar.appendChild(tocReopen);
    }

    let tocHide = tocTitle ? tocTitle.querySelector(".toc-hide-btn") : null;
    if (tocTitle && !tocHide) {
      tocHide = document.createElement("button");
      tocHide.type = "button";
      tocHide.className = "sidebar-hide-btn toc-hide-btn";
      tocHide.innerHTML = "&raquo;";
      tocHide.title = "Hide page outline";
      tocHide.setAttribute("aria-label", "Hide page outline");
      tocTitle.appendChild(tocHide);
    }

    const syncToc = (collapsed) => {
      document.body.classList.toggle("toc-collapsed", collapsed);
      tocReopen.setAttribute("aria-expanded", String(!collapsed));
    };

    const savedToc = window.localStorage && localStorage.getItem(TOC_KEY) === "1";
    syncToc(savedToc);

    const toggleToc = (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const next = !document.body.classList.contains("toc-collapsed");
      syncToc(next);
      try {
        localStorage.setItem(TOC_KEY, next ? "1" : "0");
      } catch (_) {}
    };

    if (!tocReopen.dataset.bound) {
      tocReopen.dataset.bound = "1";
      tocReopen.addEventListener("click", toggleToc);
    }
    if (tocHide && !tocHide.dataset.bound) {
      tocHide.dataset.bound = "1";
      tocHide.addEventListener("click", toggleToc);
    }
  }

  function initAll() {
    initArchitectureDiagram();
    initCollapsibleSidebars();
  }

  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(initAll);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
