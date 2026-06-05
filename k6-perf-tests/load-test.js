/**
 * LOAD TEST
 * Purpose : Simulate expected normal production traffic.
 * Pattern : Ramp up â†’ steady state â†’ ramp down.
 *   0 â†’ 25 VUs over 2 min
 *   25 VUs for 5 min
 *   25 â†’ 0 VUs over 1 min
 * Pass    : p95 < 2 s, error rate < 1%.
 */
import { check, sleep, group } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { login, runBusinessFlows, params, jsonParams } from './helpers.js';
import { BASE_URL, ENDPOINTS, THRESHOLDS } from './config.js';
import http from 'k6/http';

const loadReqDuration = new Trend('load_req_duration', true);
const loadErrorRate   = new Rate('load_error_rate');
const loadReqCount    = new Counter('load_req_count');

export const options = {
  stages: [
    { duration: '2m', target: 25 },
    { duration: '5m', target: 25 },
    { duration: '1m', target: 0  },
  ],
  thresholds: {
    http_req_duration:    ['p(95)<2000', 'p(99)<4000'],
    http_req_failed:      ['rate<0.01'],
    load_error_rate:      ['rate<0.01'],
    load_req_duration:    ['p(95)<2000'],
  },
};

export function setup() {
  const { token, workshopId } = login();
  console.log(`[LOAD] Logged in. workshopId=${workshopId}`);
  return { token, workshopId };
}

export default function (data) {
  const { token, workshopId } = data;

  group('Core Business Flows', () => {
    const responses = runBusinessFlows(token, workshopId);
    responses.forEach((res, i) => {
      const ok = res.status >= 200 && res.status < 400;
      loadReqDuration.add(res.timings.duration);
      loadErrorRate.add(!ok);
      loadReqCount.add(1);
      check(res, { [`flow_${i} ok`]: () => ok });
    });
  });

  group('Search & Lookup', () => {
    const p = params(token);

    // Technicians list
    const r1 = http.get(`${BASE_URL}${ENDPOINTS.getTechnicians}`, p);
    check(r1, { 'getTechnicians ok': (r) => r.status < 400 });
    loadReqDuration.add(r1.timings.duration);
    loadReqCount.add(1);

    // Subscription details
    const r2 = http.get(`${BASE_URL}${ENDPOINTS.subscriptionDetails}`, p);
    check(r2, { 'subscription ok': (r) => r.status < 400 });
    loadReqDuration.add(r2.timings.duration);
    loadReqCount.add(1);
  });

  sleep(Math.random() * 2 + 1); // 1â€“3 s think time
}

