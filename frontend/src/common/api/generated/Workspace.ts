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
  Channel,
  CreateFeedTokenError,
  DeleteFeedTokenError,
  FeedToken,
  ListChannelsError,
  ListModulesError,
  ModuleInput,
  ModuleUpdated,
  Ok,
  UpdateModuleError,
  UpdateModuleParams,
  WorkspaceModule,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Workspace<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Workspace
   * @name CreateFeedToken
   * @request POST:/dashboard/api/feed-token
   * @secure
   */
  createFeedToken = (params: RequestParams = {}) =>
    this.http.request<FeedToken, CreateFeedTokenError>({
      path: `/dashboard/api/feed-token`,
      method: "POST",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Workspace
   * @name DeleteFeedToken
   * @request DELETE:/dashboard/api/feed-token
   * @secure
   */
  deleteFeedToken = (params: RequestParams = {}) =>
    this.http.request<Ok, DeleteFeedTokenError>({
      path: `/dashboard/api/feed-token`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Workspace
   * @name ListChannels
   * @request GET:/dashboard/api/channels
   * @secure
   */
  listChannels = (params: RequestParams = {}) =>
    this.http.request<Channel[], ListChannelsError>({
      path: `/dashboard/api/channels`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * @description The registry is read lazily so core keeps no import-time dependency on any module.
   *
   * @tags Workspace
   * @name ListModules
   * @summary Every registered module, with whether it is active for this workspace.
   * @request GET:/dashboard/api/modules
   * @secure
   */
  listModules = (params: RequestParams = {}) =>
    this.http.request<WorkspaceModule[], ListModulesError>({
      path: `/dashboard/api/modules`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * @description Enabling a module whose scopes are not granted returns 409 rather than silently doing nothing, so the dashboard can offer a re-authorise link instead of a toggle that appears to work.
   *
   * @tags Workspace
   * @name UpdateModule
   * @summary Enable or disable one module for this workspace.
   * @request POST:/dashboard/api/modules/{name}
   * @secure
   */
  updateModule = (
    { name }: UpdateModuleParams,
    data: ModuleInput,
    params: RequestParams = {},
  ) =>
    this.http.request<ModuleUpdated, UpdateModuleError>({
      path: `/dashboard/api/modules/${name}`,
      method: "POST",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
