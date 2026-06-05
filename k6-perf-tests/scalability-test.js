/**
 * SCALABILITY TEST
 * Purpose : Measure how throughput and response time change as load grows.
 *           Each step runs for 3 minutes at a fixed VU count.
 * Pattern : Step-wise increase â†’ 5 â†’ 10 â†’ 20 â†’ 30 â†’ 40 â†’ 50 VUs.
 * Analysis: Compare p95 and RPS across steps to find the efficiency curve.
 * Pass    : No hard failure â€” observe the trend.
 */
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { login, runBusinessFlows } from './helpers.js';

const scaleReqDuration = new Trend('scale_req_duration', true);
const scaleErrorRate   = new Rate('scale_error_rate');
const scaleReqCount    = new Counter('scale_req_count');

export const options = {
  scenarios: {
    step_05_vus: {
      executor: 'constant-vus',
      vus: 5,
      duration: '3m',
      startTime: '0m',
      tags: { step: '05_vus' },
    },
    step_10_vus: {
      executor: 'constant-vus',
      vus: 10,
      duration: '3m',
      startTime: '3m',
      tags: { step: '10_vus' },
    },
    step_20_vus: {
      executor: 'constant-vus',
      vus: 20,
      duration: '3m',
      startTime: '6m',
      tags: { step: '20_vus' },
    },
    step_30_vus: {
      executor: 'constant-vus',
      vus: 30,
      duration: '3m',
      startTime: '9m',
      tags: { step: '30_vus' },
    },
    step_40_vus: {
      executor: 'constant-vus',
      vus: 40,
      duration: '3m',
      startTime: '12m',
      tags: { step: '40_vus' },
    },
    step_50_vus: {
      executor: 'constant-vus',
      vus: 50,
      duration: '3m',
      startTime: '15m',
      tags: { step: '50_vus' },
    },
  },
  thresholds: {
    http_req_duration:  ['p(95)<5000'],
    http_req_failed:    ['rate<0.05'],
    scale_error_rate:   ['rate<0.05'],
  },
};

export function setup() {
  const { token, workshopId } = login();
  console.log(`[SCALABILITY] Logged in. workshopId=${workshopId}`);
  return { token, workshopId };
}

export default function (data) {
  const responses = runBusinessFlows(data.token, data.workshopId);

  responses.forEach((res, i) => {
    const ok = res.status >= 200 && res.status < 400;
    scaleReqDuration.add(res.timings.duration);
    scaleErrorRate.add(!ok);
    scaleReqCount.add(1);
    check(res, { [`scale_flow_${i} ok`]: () => ok });
  });

  sleep(1);
}

