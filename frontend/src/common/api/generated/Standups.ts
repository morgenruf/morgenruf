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
  CreateStandupError,
  DeleteStandupError,
  DeleteStandupParams,
  ListStandupsError,
  ListTemplatesError,
  Ok,
  Standup,
  StandupInput,
  StandupTemplate,
  UpdateStandupError,
  UpdateStandupParams,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Standups<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Standups
   * @name CreateStandup
   * @request POST:/dashboard/api/standups
   * @secure
   */
  createStandup = (data: StandupInput, params: RequestParams = {}) =>
    this.http.request<Standup, CreateStandupError>({
      path: `/dashboard/api/standups`,
      method: "POST",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Standups
   * @name DeleteStandup
   * @request DELETE:/dashboard/api/standups/{standup_id}
   * @secure
   */
  deleteStandup = (
    { standupId }: DeleteStandupParams,
    params: RequestParams = {},
  ) =>
    this.http.request<Ok, DeleteStandupError>({
      path: `/dashboard/api/standups/${standupId}`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Standups
   * @name ListStandups
   * @request GET:/dashboard/api/standups
   * @secure
   */
  listStandups = (params: RequestParams = {}) =>
    this.http.request<Standup[], ListStandupsError>({
      path: `/dashboard/api/standups`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Standups
   * @name ListTemplates
   * @request GET:/dashboard/api/templates
   * @secure
   */
  listTemplates = (params: RequestParams = {}) =>
    this.http.request<StandupTemplate[], ListTemplatesError>({
      path: `/dashboard/api/templates`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Standups
   * @name UpdateStandup
   * @request PUT:/dashboard/api/standups/{standup_id}
   * @secure
   */
  updateStandup = (
    { standupId }: UpdateStandupParams,
    data: StandupInput,
    params: RequestParams = {},
  ) =>
    this.http.request<Standup, UpdateStandupError>({
      path: `/dashboard/api/standups/${standupId}`,
      method: "PUT",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
