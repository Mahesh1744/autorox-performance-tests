// Reads from environment variables in CI/CD; falls back to local defaults.
export const BASE_URL = __ENV.PERF_BASE_URL || 'https://pre.autorox.co/axprprod';

export const CREDENTIALS = {
  ssoId:    __ENV.PERF_USERNAME || 'pre3',
  password: __ENV.PERF_PASSWORD || 'Admin@123',
};

// Shared thresholds applied across all test types
export const THRESHOLDS = {
  http_req_duration: ['p(95)<3000', 'p(99)<6000'],
  http_req_failed: ['rate<0.05'],
  http_req_waiting: ['p(95)<2500'],
};

// Key API endpoints to exercise in every test
export const ENDPOINTS = {
  // Workshop core
  serviceTickets:       '/workshop/serviceTickets',
  getWorkshop:          '/workshop/getWorkShop',
  subscriptionDetails:  '/workshop/getSubscriptionDetails',
  workshopTimeSlots:    '/workshop/getWorkshopTimeSlots',

  // Service advisor flows
  ticketsByStatus:      '/serviceAdvisor/getServiceTicketsByStatus',
  serviceList:          '/serviceAdvisor/serviceList',
  getTechnicians:       '/serviceAdvisor/getTechnicians',
  searchData:           '/serviceAdvisor/searchdata',

  // Reports
  dashboardCount:       '/reports/getDashboardCount',
  wipData:              '/reports/workInProgressData',
  paymentsReport:       '/reports/paymentsReport',
  allReportList:        '/reports/getAllReportList',
};
