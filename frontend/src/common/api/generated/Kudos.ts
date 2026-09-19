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
  GetConfigError,
  GetGiversError,
  GetGiversParams,
  GetLeaderboardError,
  GetLeaderboardParams,
  KudosConfig,
  KudosConfigInput,
  KudosEntry,
  KudosGiver,
  KudosReceiver,
  ListKudosError,
  ListKudosParams,
  UpdateConfigError,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Kudos<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Kudos
   * @name GetConfig
   * @request GET:/dashboard/api/kudos/config
   * @secure
   */
  getConfig = (params: RequestParams = {}) =>
    this.http.request<KudosConfig, GetConfigError>({
      path: `/dashboard/api/kudos/config`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Kudos
   * @name GetGivers
   * @summary Who is doing the recognising. The half most tools leave out.
   * @request GET:/dashboard/api/kudos/givers
   * @secure
   */
  getGivers = (query: GetGiversParams = {}, params: RequestParams = {}) =>
    this.http.request<KudosGiver[], GetGiversError>({
      path: `/dashboard/api/kudos/givers`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Kudos
   * @name GetLeaderboard
   * @request GET:/dashboard/api/kudos/leaderboard
   * @secure
   */
  getLeaderboard = (
    query: GetLeaderboardParams = {},
    params: RequestParams = {},
  ) =>
    this.http.request<KudosReceiver[], GetLeaderboardError>({
      path: `/dashboard/api/kudos/leaderboard`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Kudos
   * @name ListKudos
   * @request GET:/dashboard/api/kudos
   * @secure
   */
  listKudos = (query: ListKudosParams = {}, params: RequestParams = {}) =>
    this.http.request<KudosEntry[], ListKudosError>({
      path: `/dashboard/api/kudos`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Kudos
   * @name UpdateConfig
   * @request POST:/dashboard/api/kudos/config
   * @secure
   */
  updateConfig = (data: KudosConfigInput, params: RequestParams = {}) =>
    this.http.request<KudosConfig, UpdateConfigError>({
      path: `/dashboard/api/kudos/config`,
      method: "POST",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
