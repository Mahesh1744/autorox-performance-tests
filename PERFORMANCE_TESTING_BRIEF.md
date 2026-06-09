# Autorox API — Performance Testing Brief

**Project:** Autorox Pre-Production API  
**Target:** `https://pre.autorox.co/axprprod/`  
**Tool:** k6 v2.0.0  
**Repo:** https://github.com/Mahesh1744/autorox-performance-tests  
**Date:** June 2026  

---

## 1. What Was Built

A complete performance testing suite covering **6 test types**, automated via **GitHub Actions CI/CD**, with an **HTML dashboard** and **JUnit XML report**.

---

## 2. Authentication Discovery

The Autorox app uses **dual-layer authentication** for REST APIs:

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| 1 | Spring Security Form Login → `JSESSIONID` cookie | Web session |
| 2 | `GET /userAccess` → JWT in `Location` header | API Bearer token |

**Login flow implemented in every test:**
```
POST /login  (ssoId=pre3, password=Admin@123)
  → JSESSIONID cookie

GET /userAccess  (Cookie: JSESSIONID)
  → Location header contains ?token=<JWT>

Decode JWT payload (base64url) → extract workshop_id = 47282

All API calls → Authorization: Bearer <JWT>
```

> **Key fix:** k6 does not support `atob()`. JWT decoding uses `k6/encoding` module's `b64decode()`.

---

## 3. Test Suite — Current Configuration (Scaled for Thousands of Users)

| Test | VUs | Duration | Purpose |
|------|-----|----------|---------|
| **Smoke** | 5 VUs | 2 min | Validate system is healthy before heavier tests |
| **Load** | 0→250→0 | 13 min | Normal expected traffic (~10% of 5K user base) |
| **Stress** | 100→1,000→0 | 14 min | Push beyond normal to find breaking point |
| **Spike** | 100→800→100 (×3) | 12 min | Sudden burst — morning check-in rush / events |
| **Soak** | 150 VUs sustained | 60 min | Detect memory leaks & degradation over time |
| **Scalability** | 50→100→200→300→500→750→1,000 | 21 min | Map performance curve step by step |

---

## 4. Endpoints Tested (12 Endpoints per Iteration)

| Endpoint | Method | Category |
|----------|--------|----------|
| `/login` | POST | Auth |
| `/userAccess` | GET | Auth |
| `/workshop/getSubscriptionDetails` | GET | Workshop |
| `/workshop/getWorkshopTimeSlots` | GET | Workshop |
| `/serviceAdvisor/getServiceTicketsByStatus` | GET | Service |
| `/serviceAdvisor/serviceList` | POST | Service |
| `/serviceAdvisor/getTechnicians` | GET | Service |
| `/serviceAdvisor/searchdata` | GET | Service |
| `/reports/getDashboardCount` | POST | Reports |
| `/reports/workInProgressData` | GET | Reports |
| `/reports/paymentsReport` | GET | Reports |
| `/reports/getAllReportList` | GET | Reports |

---

## 5. Thresholds (Pass/Fail Criteria)

| Metric | Threshold |
|--------|-----------|
| `http_req_duration` p95 | < 3,000 ms (load/soak) · < 8,000 ms (stress/spike) |
| `http_req_failed` | < 1% (load/soak) · < 10% (stress) · < 15% (spike) |
| `http_req_waiting` p95 | < 2,500 ms |

---

## 6. Baseline Results (First Full Run — June 2026)

**Overall grade: A+ (98/100) — All 6 tests passed.**

| Test | VUs | Requests | Avg (ms) | p95 (ms) | Error % |
|------|-----|----------|----------|----------|---------|
| Smoke | 1 | 722 | 43 | 112 | 0.00% |
| Load | 25 | 35,438 | 110 | 329 | 0.00% |
| Stress | 10→100 | 54,572 | 468 | 1,490 | 0.002% |
| Spike | 5→80 | 16,562 | 516 | 1,820 | 0.00% |
| Soak | 15 | 63,182 | 290 | 1,030 | 0.00% |
| Scalability | 5→50 | 69,152 | 310 | 921 | 0.00% |
| **Total** | | **229,846** | | | **0.0004%** |

*(Note: Baseline was captured at lower VU counts. New scaled tests will produce updated results.)*

---

## 7. Key Findings from Baseline

| # | Finding | Action |
|---|---------|--------|
| ✅ | Zero downtime across all tests | No action needed |
| ✅ | Auth flow stable under 100 VUs | No action needed |
| ✅ | No memory leak in 34-min soak | No action needed |
| ✅ | Spike recovery in < 60 seconds | No action needed |
| ⚠️ | p95 jumps 4.5× at 100 VUs (329ms → 1,490ms) | Review connection pool / horizontal scaling |
| ⚠️ | `/reports/paymentsReport` avg 634ms, p95 1,780ms | Run EXPLAIN ANALYZE on DB query |
| ⚠️ | `/serviceAdvisor/serviceList` avg 523ms, p95 1,420ms | Investigate N+1 query or missing index |
| 💡 | Reports endpoints change slowly | Add 60s Redis/server-side cache |

---

## 8. Project File Structure

```
autorox-performance-tests/
│
├── k6-perf-tests/
│   ├── config.js            # Shared config — base URL, credentials, endpoints, thresholds
│   ├── helpers.js           # Auth flow (login + JWT decode) + business flow runner
│   ├── smoke-test.js        # 5 VUs · 2 min
│   ├── load-test.js         # 250 VUs · 13 min
│   ├── stress-test.js       # 100→1,000 VUs · 14 min
│   ├── spike-test.js        # 100→800 VUs · 12 min
│   ├── soak-test.js         # 150 VUs · 60 min
│   ├── scalability-test.js  # 50→1,000 VUs · 21 min
│   ├── run_all.ps1          # Windows runner script
│   └── results/
│       ├── autorox_perf_dashboard.html   # Interactive HTML dashboard (Chart.js)
│       └── autorox_perf_report.xml       # JUnit XML report
│
└── .github/workflows/
    └── k6-performance.yml   # GitHub Actions CI/CD pipeline
```

---

## 9. CI/CD Pipeline (GitHub Actions)

**Triggers:**
- Every push/PR to `main` → runs **Smoke** test automatically
- Daily at 2:00 AM UTC → runs full suite
- Manual trigger → choose any single test or all

**Job flow:**
```
Smoke ──┬── Load ──┬── Stress
        │          ├── Soak
        └── Spike  └── Scalability
```

**Secrets required in GitHub repo settings:**

| Secret | Value |
|--------|-------|
| `PERF_BASE_URL` | `https://pre.autorox.co/axprprod` |
| `PERF_USERNAME` | `pre3` |
| `PERF_PASSWORD` | `Admin@123` |
| `K6_CLOUD_TOKEN` | *(Grafana Cloud token — optional for live dashboard)* |

**k6 installed via:** `grafana/setup-k6-action@v1` (replaces broken GPG keyserver install)

---

## 10. How to Run Locally (Windows)

**Prerequisites:** k6 installed — https://k6.io/docs/get-started/installation/

```powershell
# Navigate to test folder
cd "C:\Users\AX-LPT- 030\k6-perf-tests"

# Run a single test
.\run_all.ps1 -Test smoke
.\run_all.ps1 -Test load
.\run_all.ps1 -Test stress

# Run all tests in sequence
.\run_all.ps1

# Stream results live to Grafana Cloud (optional)
$env:K6_CLOUD_TOKEN = "your-token-here"
.\run_all.ps1 -Test smoke
```

**Results saved to:** `k6-perf-tests\results\`

---

## 11. Reports & Dashboard

| Report | Location | Format |
|--------|----------|--------|
| HTML Dashboard | `k6-perf-tests/results/autorox_perf_dashboard.html` | Interactive (Chart.js) |
| JUnit XML | `k6-perf-tests/results/autorox_perf_report.xml` | CI-compatible |
| GitHub Summary | Actions tab → each job run | Inline markdown |
| Artifacts | Actions tab → download per-run `.json` + `.log` | Raw k6 output |

**Dashboard includes:**
- A+ performance grade with score breakdown
- 8 KPI cards with trend indicators
- VU load shape chart (all 6 test types)
- Response time, throughput, scalability, percentile, soak trend charts
- Endpoint-level breakdown table (12 endpoints)
- 8 findings & recommendations cards
- Dark/light mode toggle + print button

---

## 12. Known Issues / Workarounds

| Issue | Root Cause | Fix Applied |
|-------|-----------|-------------|
| `atob()` not available in k6 | k6 runtime does not expose browser globals | Use `k6/encoding` `b64decode()` |
| `displayWorkShopDetails` returns HTTP 500 | Server-side circular view path bug | Replaced with `/serviceAdvisor/getTechnicians` |
| GitHub Actions k6 install fails (GPG error) | `hkp://keyserver.ubuntu.com:80` blocked on GitHub runners | Use `grafana/setup-k6-action@v1` |
| Login field is `ssoId` not `username` | Autorox uses custom field name | Confirmed via HTML form inspection |

---

## 13. Next Recommended Steps

| Priority | Task |
|----------|------|
| High | Run scaled tests (250→1,000 VU range) and capture new baseline |
| High | Add Slack/email notifications when GitHub Actions thresholds breach |
| High | Performance regression gate — fail CI if p95 degrades > 20% vs previous run |
| Medium | Expand endpoint coverage (currently 12 of 1,312 Swagger endpoints) |
| Medium | Add Redis caching to reports endpoints (paymentsReport, serviceList) |
| Medium | Run breakpoint test at 1,200–1,500 VUs to find exact saturation point |
| Low | Data-driven testing with CSV of real VIN numbers / workshop IDs |

---

*Generated by Claude Code · Autorox QA Team · June 2026*
