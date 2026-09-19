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
  GetInsightsError,
  GetInsightsParams,
  GetTodayError,
  GetTodayParams,
  InsightsData,
  Today,
} from "./data-contracts";
import { HttpClient, type RequestParams } from "./http-client";

export class Insights<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Insights
   * @name GetInsights
   * @request GET:/dashboard/api/insights
   * @secure
   */
  getInsights = (query: GetInsightsParams = {}, params: RequestParams = {}) =>
    this.http.request<InsightsData, GetInsightsError>({
      path: `/dashboard/api/insights`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * @description Every piece is optional on purpose. A workspace with no schedules, no kudos or no coffee chats still gets a page, because each query returns empty rather than raising and the counts fall out of whatever arrived.
   *
   * @tags Insights
   * @name GetToday
   * @summary One morning, in one request.
   * @request GET:/dashboard/api/today
   * @secure
   */
  getToday = (query: GetTodayParams = {}, params: RequestParams = {}) =>
    this.http.request<Today, GetTodayError>({
      path: `/dashboard/api/today`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
}
