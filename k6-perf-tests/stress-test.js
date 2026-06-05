/**
 * STRESS TEST
 * Purpose : Push the system beyond normal load to find the breaking point.
 *           Observe at which VU count errors spike or response time degrades.
 * Pattern : Step-up in 5 stages, each 2 min, then rapid ramp-down.
 *   Stage 1:  10 VUs
 *   Stage 2:  25 VUs
 *   Stage 3:  50 VUs
 *   Stage 4:  75 VUs
 *   Stage 5: 100 VUs
 *   Ramp-down: 0 VUs (1 min)
 * Pass    : p95 < 5 s, error rate < 10% (intentionally lenient to measure degr.)
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
    { duration: '2m', target: 10  },
    { duration: '2m', target: 25  },
    { duration: '2m', target: 50  },
    { duration: '2m', target: 75  },
    { duration: '2m', target: 100 },
    { duration: '1m', target: 0   },
  ],
  thresholds: {
    http_req_duration:    ['p(95)<5000'],
    http_req_failed:      ['rate<0.10'],
    stress_error_rate:    ['rate<0.10'],
    stress_req_duration:  ['p(95)<5000'],
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
  const elapsed = (Date.now() / 1000) % (11 * 60); // rough stage estimation
  if (elapsed < 120)  return '10vus';
  if (elapsed < 240)  return '25vus';
  if (elapsed < 360)  return '50vus';
  if (elapsed < 480)  return '75vus';
  if (elapsed < 600)  return '100vus';
  return 'rampdown';
}

