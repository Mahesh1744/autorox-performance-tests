import http from 'k6/http';
import { check } from 'k6';
import encoding from 'k6/encoding';
import { BASE_URL, CREDENTIALS, ENDPOINTS } from './config.js';

/**
 * Full login flow:
 *  1. POST /login  → get JSESSIONID (302)
 *  2. GET  /userAccess (no redirect) → extract JWT from Location header
 *  3. Decode JWT payload → extract workshop_id
 *
 * Returns { token, workshopId }
 */
export function login() {
  // Step 1 — form login
  const loginRes = http.post(
    `${BASE_URL}/login`,
    `ssoId=${CREDENTIALS.ssoId}&password=${CREDENTIALS.password}&csrf_token=dummy`,
    {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      redirects: 0,
    }
  );
  check(loginRes, { 'login returns 302': (r) => r.status === 302 });

  const jar = loginRes.cookies['JSESSIONID'];
  if (!jar || jar.length === 0) {
    throw new Error(`Login failed — status ${loginRes.status}, no JSESSIONID`);
  }
  const jsessionid = jar[0].value;

  // Step 2 — follow to /userAccess without chasing the second redirect so we
  // can read the Location header that contains the JWT token
  const accessRes = http.get(
    `${BASE_URL}/userAccess`,
    { headers: { Cookie: `JSESSIONID=${jsessionid}` }, redirects: 0 }
  );

  const location = accessRes.headers['Location'] || '';
  const tokenMatch = location.match(/[?&]token=([^&]+)/);
  if (!tokenMatch) {
    throw new Error(`Could not extract JWT from Location header: ${location}`);
  }
  const token = tokenMatch[1];

  // Step 3 — decode JWT payload (middle segment) to get workshopId
  const workshopId = extractWorkshopId(token);

  return { token, workshopId };
}

// Decode the JWT payload (no verification) and extract workshop_id.
function extractWorkshopId(jwt) {
  try {
    const payload = jwt.split('.')[1];
    // Convert base64url → base64 standard, then decode via k6/encoding
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const json = JSON.parse(encoding.b64decode(b64, 'std', 's'));
    return json.workshop_id || json.workshopId || 1;
  } catch (e) {
    console.warn(`JWT decode failed: ${e}`);
    return 1;
  }
}

// Build k6 request params with Bearer token header.
export function params(token, extra) {
  return Object.assign(
    { headers: { Authorization: `Bearer ${token}` } },
    extra || {}
  );
}

// Build params with JSON content-type + Bearer token.
export function jsonParams(token) {
  return {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  };
}

// Run the core business-flow requests used by all test types.
// Returns an array of response objects for the caller to check.
export function runBusinessFlows(token, workshopId) {
  const today = new Date();
  const from  = fmtDate(new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000));
  const to    = fmtDate(today);
  const p     = params(token);
  const jp    = jsonParams(token);
  const wid   = workshopId || 1;

  const results = [];

  // 1. Tickets by status – OPEN
  results.push(http.get(
    `${BASE_URL}${ENDPOINTS.ticketsByStatus}?status=OPEN&pageNo=0&workShopId=${wid}`, p
  ));

  // 2. Tickets by status – CLOSED
  results.push(http.get(
    `${BASE_URL}${ENDPOINTS.ticketsByStatus}?status=CLOSED&pageNo=0&workShopId=${wid}`, p
  ));

  // 3. Work-in-progress report
  results.push(http.get(
    `${BASE_URL}${ENDPOINTS.wipData}?workShopId=${wid}&fromdate=${from}&todate=${to}&pageNo=0&pagecount=20`, p
  ));

  // 4. Payments report
  results.push(http.get(
    `${BASE_URL}${ENDPOINTS.paymentsReport}?workShopId=${wid}&fromdate=${from}&todate=${to}`, p
  ));

  // 5. Dashboard count (POST JSON)
  results.push(http.post(
    `${BASE_URL}${ENDPOINTS.dashboardCount}`,
    JSON.stringify({ workShopId: String(wid), fromdate: from, todate: to }),
    jp
  ));

  // 6. Service list (POST)
  results.push(http.post(`${BASE_URL}${ENDPOINTS.serviceList}`, null, jp));

  // 7. All report list
  results.push(http.get(`${BASE_URL}${ENDPOINTS.allReportList}`, p));

  // 8. Workshop time slots
  results.push(http.get(
    `${BASE_URL}${ENDPOINTS.workshopTimeSlots}?workshopId=${wid}`, p
  ));

  // 9. Subscription details
  results.push(http.get(`${BASE_URL}${ENDPOINTS.subscriptionDetails}`, p));

  // 10. Technicians list
  results.push(http.get(`${BASE_URL}${ENDPOINTS.getTechnicians}`, p));

  return results;
}

function fmtDate(d) {
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}-${mm}-${d.getFullYear()}`;
}
