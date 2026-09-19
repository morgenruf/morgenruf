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
  AnalyticsData,
  GetAnalyticsError,
  GetAnalyticsParams,
  GetStatsError,
  Stats,
} from "./data-contracts";
import { HttpClient, type RequestParams } from "./http-client";

export class Analytics<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * @description Members in no active schedule stay in the list with `enrolled` false and an expected count of 0, so the UI can render them as "not enrolled" instead of a misleading "0 of 7".
   *
   * @tags Analytics
   * @name GetAnalytics
   * @summary Per-member participation for the last N days.
   * @request GET:/dashboard/api/analytics
   * @secure
   */
  getAnalytics = (query: GetAnalyticsParams = {}, params: RequestParams = {}) =>
    this.http.request<AnalyticsData, GetAnalyticsError>({
      path: `/dashboard/api/analytics`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Analytics
   * @name GetStats
   * @request GET:/dashboard/api/stats
   * @secure
   */
  getStats = (params: RequestParams = {}) =>
    this.http.request<Stats, GetStatsError>({
      path: `/dashboard/api/stats`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
}
