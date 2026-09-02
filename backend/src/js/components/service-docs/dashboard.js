// ABOUTME: Dashboard tab of the service docs console - MOCK results-dashboard services (ticket 886)
// ABOUTME: One of the per-tab slices composed into serviceDocsController

/**
 * Build the dashboard slice of the service docs controller.
 *
 * These three services are MOCKS (see service_layer/dashboard_stats.py): they
 * return fixture data so the results-dashboard front-end can be built before the
 * real queries exist. Flat properties, because the CSP Alpine build's x-model
 * cannot use a nested path. executeService, copyResponse and copyToClipboard come
 * from the core slice once merged.
 *
 * @returns {Object} a flat slice of Alpine component state
 */
export function serviceDocsDashboard() {
  return {
    dashboardSummaryAssemblyId: "",
    dashboardReportAssemblyId: "",
    dashboardExportAssemblyId: "",
    dashboardExportFormat: "csv",

    executeGetDashboardSummary: function () {
      return this.executeService("get_assembly_dashboard_summary", {
        assembly_id: this.dashboardSummaryAssemblyId,
      });
    },

    executeGetDashboardReport: function () {
      return this.executeService("get_assembly_dashboard_report", {
        assembly_id: this.dashboardReportAssemblyId,
      });
    },

    executeExportDashboard: function () {
      return this.executeService("export_assembly_dashboard", {
        assembly_id: this.dashboardExportAssemblyId,
        export_format: this.dashboardExportFormat,
      });
    },

    copyDashboardSummaryResponse: function () {
      return this.copyResponse("dashboard_summary");
    },

    copyDashboardReportResponse: function () {
      return this.copyResponse("dashboard_report");
    },

    copyDashboardExportResponse: function () {
      return this.copyResponse("dashboard_export");
    },
  };
}
