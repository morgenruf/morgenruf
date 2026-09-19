/* eslint-disable */
/* tslint:disable */
// @ts-nocheck
/*
 * ---------------------------------------------------------------
 * ## THIS FILE WAS GENERATED VIA SWAGGER-TYPESCRIPT-API        ##
 * ##                                                           ##
 * ## AUTHOR: acacode                                           ##
 * ## SOURCE: https://github.com/acacode/swagger-typescript-api ##
 * ---------------------------------------------------------------
 */

import type {
  ExportCsvError,
  ExportCsvParams,
  GetReportsError,
  GetReportsParams,
  ReportsData,
} from "./data-contracts";
import { HttpClient, type RequestParams } from "./http-client";

export class Reports<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Reports
   * @name ExportCsv
   * @request GET:/dashboard/api/export/csv
   * @secure
   */
  exportCsv = (query: ExportCsvParams = {}, params: RequestParams = {}) =>
    this.http.request<File, ExportCsvError>({
      path: `/dashboard/api/export/csv`,
      method: "GET",
      query: query,
      secure: true,
      ...params,
    });
  /**
   * No description
   *
   * @tags Reports
   * @name GetReports
   * @summary Return standup history with participation stats, filterable by date/member.
   * @request GET:/dashboard/api/reports
   * @secure
   */
  getReports = (query: GetReportsParams = {}, params: RequestParams = {}) =>
    this.http.request<ReportsData, GetReportsError>({
      path: `/dashboard/api/reports`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
}
