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
  GetSessionError,
  LogoutError,
  Ok,
  SessionInfo,
} from "./data-contracts";
import { HttpClient, type RequestParams } from "./http-client";

export class Session<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Session
   * @name GetSession
   * @request GET:/dashboard/api/me
   * @secure
   */
  getSession = (params: RequestParams = {}) =>
    this.http.request<SessionInfo, GetSessionError>({
      path: `/dashboard/api/me`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Session
   * @name Logout
   * @request POST:/dashboard/api/logout
   * @secure
   */
  logout = (params: RequestParams = {}) =>
    this.http.request<Ok, LogoutError>({
      path: `/dashboard/api/logout`,
      method: "POST",
      secure: true,
      format: "json",
      ...params,
    });
}
