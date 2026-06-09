/**
 * STRESS TEST
 * Purpose : Push system beyond normal load to find the breaking point.
 *           Observe at which VU count errors spike or response time degrades.
 * Pattern : Step-up in 6 stages (2 min each), then ramp-down.
 *   Stage 1:  100 VUs
 *   Stage 2:  250 VUs
 *   Stage 3:  500 VUs
 *   Stage 4:  750 VUs
 *   Stage 5: 1000 VUs
 *   Stage 6: 1000 VUs (hold - observe sustained stress)
 *   Ramp-down: 0 VUs (2 min)
 * Total   : 14 min
 * Pass    : p95 < 8 s, error rate < 10% (lenient - goal is to measure degradation)
 */
import { check, sleep, group } from 'k6';
import { Trend, Rate, Counter, Gauge } from 'k6/metrics';
import { login, runBusinessFlows } from './helpers.js';

const stressReqDuration  = new Trend('stress_req_duration', true);
const stressErrorRate    = new Rate('stress_error_rate');
const stressReqCount     = new Counter('stress_req_count');
const stressActiveVUs    = new Gauge('stress_active_vus');

export const options = {
  stages: [
    { duration: '2m', target: 100  },
    { duration: '2m', target: 250  },
    { duration: '2m', target: 500  },
    { duration: '2m', target: 750  },
    { duration: '2m', target: 1000 },
    { duration: '2m', target: 1000 },
    { duration: '2m', target: 0    },
  ],
  thresholds: {
    http_req_duration:    ['p(95)<8000'],
    http_req_failed:      ['rate<0.10'],
    stress_error_rate:    ['rate<0.10'],
    stress_req_duration:  ['p(95)<8000'],
  },
};

export function setup() {
  const { token, workshopId } = login();
  console.log(`[STRESS] Logged in. workshopId=${workshopId}`);
  return { token, workshopId };
}

export default function (data) {
  stressActiveVUs.add(__VU);

  group('Stress Flows', () => {
    const responses = runBusinessFlows(data.token, data.workshopId);
    responses.forEach((res, i) => {
      const ok = res.status >= 200 && res.status < 400;
      stressReqDuration.add(res.timings.duration, { stage: currentStage() });
      stressErrorRate.add(!ok);
      stressReqCount.add(1);
      check(res, { [`stress_flow_${i} ok`]: () => ok });
    });
  });

  sleep(0.5); // minimal think time to maximise stress
}

function currentStage() {
  const elapsed = (Date.now() / 1000) % (14 * 60);
  if (elapsed < 120)  return '100vus';
  if (elapsed < 240)  return '250vus';
  if (elapsed < 360)  return '500vus';
  if (elapsed < 480)  return '750vus';
  if (elapsed < 600)  return '1000vus';
  if (elapsed < 720)  return '1000vus_hold';
  return 'rampdown';
}

