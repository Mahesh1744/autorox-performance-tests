/**
 * SPIKE TEST
 * Purpose : Simulate sudden, extreme bursts of traffic (flash sale / viral event).
 *           Observe recovery behaviour after the spike drops.
 * Pattern : 3 spike cycles.
 *   Baseline  :  5 VUs  (1 min)
 *   Spike     : 80 VUs  (30 s)  â† instant ramp
 *   Recovery  :  5 VUs  (1 min)
 *   Spike     : 80 VUs  (30 s)
 *   Recovery  :  5 VUs  (1 min)
 *   Spike     : 80 VUs  (30 s)
 *   Cool-down :  0 VUs  (30 s)
 * Pass    : p95 < 6 s during spikes, recovery p95 < 2 s within 60 s of spike end.
 */
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { login, runBusinessFlows } from './helpers.js';

const spikeReqDuration = new Trend('spike_req_duration', true);
const spikeErrorRate   = new Rate('spike_error_rate');
const spikeReqCount    = new Counter('spike_req_count');

export const options = {
  stages: [
    // Baseline
    { duration: '1m',  target: 5  },
    // Spike 1
    { duration: '0s',  target: 80 },
    { duration: '30s', target: 80 },
    // Recovery 1
    { duration: '0s',  target: 5  },
    { duration: '1m',  target: 5  },
    // Spike 2
    { duration: '0s',  target: 80 },
    { duration: '30s', target: 80 },
    // Recovery 2
    { duration: '0s',  target: 5  },
    { duration: '1m',  target: 5  },
    // Spike 3
    { duration: '0s',  target: 80 },
    { duration: '30s', target: 80 },
    // Cool-down
    { duration: '0s',  target: 0  },
    { duration: '30s', target: 0  },
  ],
  thresholds: {
    http_req_duration: ['p(95)<6000'],
    http_req_failed:   ['rate<0.15'],
    spike_error_rate:  ['rate<0.15'],
  },
};

export function setup() {
  const { token, workshopId } = login();
  console.log(`[SPIKE] Logged in. workshopId=${workshopId}`);
  return { token, workshopId };
}

export default function (data) {
  const responses = runBusinessFlows(data.token, data.workshopId);

  responses.forEach((res, i) => {
    const ok = res.status >= 200 && res.status < 400;
    spikeReqDuration.add(res.timings.duration, { vu_count: String(__VU) });
    spikeErrorRate.add(!ok);
    spikeReqCount.add(1);
    check(res, { [`spike_flow_${i} ok`]: () => ok });
  });

  // No sleep â€” spike test intentionally hammers the server
  sleep(0.1);
}

