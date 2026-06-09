/**
 * BREAKPOINT TEST
 * Purpose : Find the exact VU count where the system breaks under load.
 *           The test auto-stops when error rate exceeds 10% for 30 seconds.
 * Pattern : Ramp 100 VUs per minute from 100 to 2,000 VUs.
 *   Stage  1:  100 VUs (1 min)
 *   Stage  2:  200 VUs (1 min)
 *   Stage  3:  300 VUs (1 min)
 *   ...
 *   Stage 13: 2,000 VUs (1 min) <- unlikely to reach
 *   Ramp-down: 0 VUs (1 min)
 * Total   : up to 14 min (usually stops early at breakpoint)
 * Output  : The VU count at time of abort = system breakpoint.
 * Pass    : Test always "fails" - this is expected. Goal is the data, not pass/fail.
 */
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { login, runBusinessFlows } from './helpers.js';

const bpErrorRate    = new Rate('breakpoint_error_rate');
const bpReqDuration  = new Trend('breakpoint_req_duration', true);

export const options = {
  stages: [
    { duration: '1m', target: 100  },
    { duration: '1m', target: 200  },
    { duration: '1m', target: 300  },
    { duration: '1m', target: 400  },
    { duration: '1m', target: 500  },
    { duration: '1m', target: 600  },
    { duration: '1m', target: 700  },
    { duration: '1m', target: 800  },
    { duration: '1m', target: 900  },
    { duration: '1m', target: 1000 },
    { duration: '1m', target: 1200 },
    { duration: '1m', target: 1500 },
    { duration: '1m', target: 2000 },
    { duration: '1m', target: 0    },
  ],
  thresholds: {
    // abortOnFail stops the test the moment error rate crosses 10%
    // delayAbortEval gives 30s grace period to rule out transient spikes
    http_req_failed: [{
      threshold: 'rate<0.10',
      abortOnFail: true,
      delayAbortEval: '30s',
    }],
    breakpoint_error_rate: [{
      threshold: 'rate<0.10',
      abortOnFail: true,
      delayAbortEval: '30s',
    }],
    http_req_duration: [{ threshold: 'p(95)<15000', abortOnFail: false }],
  },
};

export function setup() {
  const { token, workshopId } = login();
  console.log(`[BREAKPOINT] Logged in. workshopId=${workshopId}`);
  console.log('[BREAKPOINT] Test will auto-abort when error rate > 10% for 30s.');
  console.log('[BREAKPOINT] Check the active VU count at abort = system breakpoint.');
  return { token, workshopId };
}

export default function (data) {
  const responses = runBusinessFlows(data.token, data.workshopId);

  responses.forEach((res, i) => {
    const ok = res.status >= 200 && res.status < 400;
    bpErrorRate.add(!ok);
    bpReqDuration.add(res.timings.duration, { vus: String(__VU) });
    check(res, { [`bp_flow_${i} ok`]: () => ok });
  });

  sleep(0.5);
}

export function teardown(data) {
  console.log('[BREAKPOINT] Test ended. Check "vus" value at abort time in the summary.');
  console.log('[BREAKPOINT] That VU count is your system breakpoint.');
}
