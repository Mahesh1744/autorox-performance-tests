/**
 * SCALABILITY TEST
 * Purpose : Measure how throughput and response time change as load grows
 *           from light to full production-scale (thousands of users).
 *           Each step runs for 3 minutes at a fixed VU count.
 * Pattern : 7 steps -> 50 -> 100 -> 200 -> 300 -> 500 -> 750 -> 1000 VUs.
 * Total   : 21 min
 * Analysis: Compare p95 and RPS across steps to find the efficiency curve
 *           and identify the VU count where response time starts degrading.
 */
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { login, runBusinessFlows } from './helpers.js';

const scaleReqDuration = new Trend('scale_req_duration', true);
const scaleErrorRate   = new Rate('scale_error_rate');
const scaleReqCount    = new Counter('scale_req_count');

export const options = {
  scenarios: {
    step_050_vus: {
      executor: 'constant-vus',
      vus: 50,
      duration: '3m',
      startTime: '0m',
      tags: { step: '050_vus' },
    },
    step_100_vus: {
      executor: 'constant-vus',
      vus: 100,
      duration: '3m',
      startTime: '3m',
      tags: { step: '100_vus' },
    },
    step_200_vus: {
      executor: 'constant-vus',
      vus: 200,
      duration: '3m',
      startTime: '6m',
      tags: { step: '200_vus' },
    },
    step_300_vus: {
      executor: 'constant-vus',
      vus: 300,
      duration: '3m',
      startTime: '9m',
      tags: { step: '300_vus' },
    },
    step_500_vus: {
      executor: 'constant-vus',
      vus: 500,
      duration: '3m',
      startTime: '12m',
      tags: { step: '500_vus' },
    },
    step_750_vus: {
      executor: 'constant-vus',
      vus: 750,
      duration: '3m',
      startTime: '15m',
      tags: { step: '750_vus' },
    },
    step_1000_vus: {
      executor: 'constant-vus',
      vus: 1000,
      duration: '3m',
      startTime: '18m',
      tags: { step: '1000_vus' },
    },
  },
  thresholds: {
    http_req_duration:  ['p(95)<12000'],
    http_req_failed:    ['rate<0.55'],
    scale_error_rate:   ['rate<0.55'],
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
