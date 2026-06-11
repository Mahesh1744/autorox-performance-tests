/**
 * SCALABILITY TEST
 * Purpose : Measure how throughput and response time change as load grows.
 *           Each step runs for 3 minutes at a fixed VU count.
 * Pattern : 6 steps -> 25 -> 50 -> 100 -> 200 -> 350 -> 500 VUs.
 * Total   : 18 min
 * Analysis: Compare p95 and RPS across steps to find the efficiency curve.
 *           Server healthy below ~300 VUs; degradation visible at 350-500 VUs.
 */
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { login, runBusinessFlows } from './helpers.js';

const scaleReqDuration = new Trend('scale_req_duration', true);
const scaleErrorRate   = new Rate('scale_error_rate');
const scaleReqCount    = new Counter('scale_req_count');

export const options = {
  scenarios: {
    step_025_vus: {
      executor: 'constant-vus',
      vus: 25,
      duration: '3m',
      startTime: '0m',
      tags: { step: '025_vus' },
    },
    step_050_vus: {
      executor: 'constant-vus',
      vus: 50,
      duration: '3m',
      startTime: '3m',
      tags: { step: '050_vus' },
    },
    step_100_vus: {
      executor: 'constant-vus',
      vus: 100,
      duration: '3m',
      startTime: '6m',
      tags: { step: '100_vus' },
    },
    step_200_vus: {
      executor: 'constant-vus',
      vus: 200,
      duration: '3m',
      startTime: '9m',
      tags: { step: '200_vus' },
    },
    step_350_vus: {
      executor: 'constant-vus',
      vus: 350,
      duration: '3m',
      startTime: '12m',
      tags: { step: '350_vus' },
    },
    step_500_vus: {
      executor: 'constant-vus',
      vus: 500,
      duration: '3m',
      startTime: '15m',
      tags: { step: '500_vus' },
    },
  },
  thresholds: {
    http_req_duration:  ['p(95)<10000'],
    http_req_failed:    ['rate<0.40'],
    scale_error_rate:   ['rate<0.40'],
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
