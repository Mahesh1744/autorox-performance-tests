/**
 * SMOKE TEST
 * Purpose : Verify the system responds correctly under minimal load.
 * Pattern : 1 VU, 2 minutes.
 * Pass    : All key endpoints return 2xx/3xx and p95 < 3 s.
 */
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';
import { THRESHOLDS } from './config.js';
import { login, runBusinessFlows } from './helpers.js';

const reqDuration = new Trend('smoke_req_duration', true);
const errorRate   = new Rate('smoke_error_rate');

export const options = {
  vus: 1,
  duration: '2m',
  thresholds: {
    ...THRESHOLDS,
    smoke_error_rate: ['rate<0.01'],
  },
};

export function setup() {
  const { token, workshopId } = login();
  console.log(`[SMOKE] Logged in. workshopId=${workshopId}`);
  return { token, workshopId };
}

export default function (data) {
  const responses = runBusinessFlows(data.token, data.workshopId);

  const endpointNames = [
    'ticketsByStatus_OPEN',
    'ticketsByStatus_CLOSED',
    'wipData',
    'paymentsReport',
    'dashboardCount',
    'serviceList',
    'allReportList',
    'workshopTimeSlots',
    'subscriptionDetails',
    'getTechnicians',
  ];

  responses.forEach((res, i) => {
    const name = endpointNames[i] || `endpoint_${i}`;
    const ok = res.status >= 200 && res.status < 400;

    check(res, {
      [`${name} status ok`]: () => ok,
      [`${name} body not empty`]: (r) => r.body && r.body.length > 0,
    });

    reqDuration.add(res.timings.duration, { endpoint: name });
    errorRate.add(!ok);
  });

  sleep(1);
}

export function teardown(data) {
  console.log('[SMOKE] Test complete.');
}
