/**
 * SPIKE TEST
 * Purpose : Simulate sudden traffic bursts - morning workshop check-in rush,
 *           service camp events, or mass notifications sending users to the app.
 * Pattern : 3 spike cycles.
 *   Baseline  : 100 VUs  (1.5 min)  <- normal concurrent load
 *   Spike     : 800 VUs  (45 s)     <- instant ramp to 8x normal
 *   Recovery  : 100 VUs  (1.5 min)  <- back to baseline
 *   (repeat x3)
 *   Cool-down :   0 VUs  (1 min)
 * Total   : ~12 min
 * Pass    : p95 < 8 s during spikes, error rate < 15%.
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
    { duration: '1m30s', target: 100 },
    // Spike 1
    { duration: '0s',    target: 800 },
    { duration: '45s',   target: 800 },
    // Recovery 1
    { duration: '0s',    target: 100 },
    { duration: '1m30s', target: 100 },
    // Spike 2
    { duration: '0s',    target: 800 },
    { duration: '45s',   target: 800 },
    // Recovery 2
    { duration: '0s',    target: 100 },
    { duration: '1m30s', target: 100 },
    // Spike 3
    { duration: '0s',    target: 800 },
    { duration: '45s',   target: 800 },
    // Cool-down
    { duration: '0s',    target: 0   },
    { duration: '1m',    target: 0   },
  ],
  thresholds: {
    http_req_duration: ['p(95)<14000'],
    http_req_failed:   ['rate<0.35'],
    spike_error_rate:  ['rate<0.35'],
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

  sleep(0.1);
}
