/**
 * SOAK / ENDURANCE TEST
 * Purpose : Detect memory leaks, connection pool exhaustion, and gradual
 *           performance degradation under sustained production-level load.
 * Pattern : 150 VUs for 60 minutes (1 hour).
 *   0 -> 150 VUs  (3 min ramp-up)
 *   150 VUs       (55 min steady - represents ~3% of 5K user base concurrent)
 *   150 -> 0 VUs  (2 min ramp-down)
 * Total   : 60 min
 * Pass    : p95 < 3 s throughout, error rate < 1%.
 */
import { check, sleep, group } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { login, runBusinessFlows, params } from './helpers.js';
import { BASE_URL, ENDPOINTS } from './config.js';
import http from 'k6/http';

const soakReqDuration = new Trend('soak_req_duration', true);
const soakErrorRate   = new Rate('soak_error_rate');
const soakReqCount    = new Counter('soak_req_count');

export const options = {
  stages: [
    { duration: '3m',  target: 150 },
    { duration: '55m', target: 150 },
    { duration: '2m',  target: 0   },
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000', 'p(99)<5000'],
    http_req_failed:   ['rate<0.01'],
    soak_error_rate:   ['rate<0.01'],
    soak_req_duration: ['p(95)<3000'],
  },
};

export function setup() {
  const { token, workshopId } = login();
  console.log(`[SOAK] Logged in. workshopId=${workshopId}`);
  return { token, workshopId };
}

export default function (data) {
  const { token, workshopId } = data;

  group('Core Flows', () => {
    const responses = runBusinessFlows(token, workshopId);
    responses.forEach((res, i) => {
      const ok = res.status >= 200 && res.status < 400;
      soakReqDuration.add(res.timings.duration, { bucket: timeBucket() });
      soakErrorRate.add(!ok);
      soakReqCount.add(1);
      check(res, { [`soak_flow_${i} ok`]: () => ok });
    });
  });

  group('Subscription & Features', () => {
    const p = params(token);
    const r1 = http.get(`${BASE_URL}${ENDPOINTS.subscriptionDetails}`, p);
    const r2 = http.get(`${BASE_URL}${ENDPOINTS.searchData}`, p);
    [r1, r2].forEach((r) => {
      soakReqDuration.add(r.timings.duration, { bucket: timeBucket() });
      soakReqCount.add(1);
      soakErrorRate.add(r.status >= 400 ? 1 : 0);
    });
  });

  sleep(2); // 2 s think time -> realistic sustained concurrency
}

// Buckets responses into 5-minute windows for trend analysis
function timeBucket() {
  return `min_${Math.floor((__ITER * 2) / 300) * 5}`;
}
