/**
 * SPIKE TEST
 * Purpose : Simulate sudden traffic bursts - morning workshop open rush,
 *           batch notifications, or service camp events.
 * Pattern : 2 spike cycles (realistic 6x surge for B2B workshop app).
 *   Baseline  :  50 VUs  (1 min)    <- normal concurrent load
 *   Spike     : 300 VUs  (45 s)     <- instant ramp to 6x normal
 *   Recovery  :  50 VUs  (1.5 min)  <- back to baseline
 *   (repeat x2)
 *   Cool-down :   0 VUs  (1 min)
 * Total   : ~7 min
 * Pass    : p95 < 8 s during spikes, error rate < 20%.
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
    { duration: '1m',    target: 50  },
    // Spike 1
    { duration: '0s',    target: 300 },
    { duration: '45s',   target: 300 },
    // Recovery 1
    { duration: '0s',    target: 50  },
    { duration: '1m30s', target: 50  },
    // Spike 2
    { duration: '0s',    target: 300 },
    { duration: '45s',   target: 300 },
    // Recovery 2
    { duration: '0s',    target: 50  },
    { duration: '1m30s', target: 50  },
    // Cool-down
    { duration: '0s',    target: 0   },
    { duration: '1m',    target: 0   },
  ],
  thresholds: {
    http_req_duration: ['p(95)<8000'],
    http_req_failed:   ['rate<0.20'],
    spike_error_rate:  ['rate<0.20'],
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
