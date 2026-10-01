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
  GetPulseSettingsError,
  GetPulseTrendError,
  PulseRound,
  PulseSettings,
  PulseSettingsInput,
  UpdatePulseSettingsError,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Pulse<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Pulse
   * @name GetPulseSettings
   * @request GET:/dashboard/api/pulse/settings
   * @secure
   */
  getPulseSettings = (params: RequestParams = {}) =>
    this.http.request<PulseSettings, GetPulseSettingsError>({
      path: `/dashboard/api/pulse/settings`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Pulse
   * @name GetPulseTrend
   * @summary Team results per round, oldest first. Rounds under five carry counts only.
   * @request GET:/dashboard/api/pulse/trend
   * @secure
   */
  getPulseTrend = (params: RequestParams = {}) =>
    this.http.request<PulseRound[], GetPulseTrendError>({
      path: `/dashboard/api/pulse/trend`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Pulse
   * @name UpdatePulseSettings
   * @request PUT:/dashboard/api/pulse/settings
   * @secure
   */
  updatePulseSettings = (
    data: PulseSettingsInput,
    params: RequestParams = {},
  ) =>
    this.http.request<PulseSettings, UpdatePulseSettingsError>({
      path: `/dashboard/api/pulse/settings`,
      method: "PUT",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
