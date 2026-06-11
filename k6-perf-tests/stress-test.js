/**
 * STRESS TEST
 * Purpose : Push system past normal load, pinpoint where degradation begins.
 *           Server healthy below ~300 VUs, starts cracking at 400-500 VUs.
 * Pattern : Step-up in 6 stages (2 min each), then ramp-down.
 *   Stage 1: 100 VUs  (healthy zone)
 *   Stage 2: 200 VUs  (healthy zone)
 *   Stage 3: 300 VUs  (edge of healthy)
 *   Stage 4: 400 VUs  (degradation begins)
 *   Stage 5: 500 VUs  (clear degradation)
 *   Stage 6: 600 VUs  (stress peak - observe breaking behavior)
 *   Ramp-down: 0 VUs (2 min)
 * Total   : 14 min
 * Pass    : p95 < 11 s, error rate < 30% (lenient - goal is degradation curve)
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
    { duration: '2m', target: 100 },
    { duration: '2m', target: 200 },
    { duration: '2m', target: 300 },
    { duration: '2m', target: 400 },
    { duration: '2m', target: 500 },
    { duration: '2m', target: 600 },
    { duration: '2m', target: 0   },
  ],
  thresholds: {
    http_req_duration:    ['p(95)<11000'],
    http_req_failed:      ['rate<0.30'],
    stress_error_rate:    ['rate<0.30'],
    stress_req_duration:  ['p(95)<11000'],
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

