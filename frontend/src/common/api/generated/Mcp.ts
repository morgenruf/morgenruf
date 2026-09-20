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
  CreateKeyError,
  ListKeysError,
  McpKeyCreated,
  McpKeyInput,
  McpKeys,
  Ok,
  RevokeKeyError,
  RevokeKeyParams,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Mcp<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Mcp
   * @name CreateKey
   * @request POST:/dashboard/api/mcp/keys
   * @secure
   */
  createKey = (data: McpKeyInput, params: RequestParams = {}) =>
    this.http.request<McpKeyCreated, CreateKeyError>({
      path: `/dashboard/api/mcp/keys`,
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
   * @tags Mcp
   * @name ListKeys
   * @request GET:/dashboard/api/mcp/keys
   * @secure
   */
  listKeys = (params: RequestParams = {}) =>
    this.http.request<McpKeys, ListKeysError>({
      path: `/dashboard/api/mcp/keys`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Mcp
   * @name RevokeKey
   * @request DELETE:/dashboard/api/mcp/keys/{key_id}
   * @secure
   */
  revokeKey = ({ keyId }: RevokeKeyParams, params: RequestParams = {}) =>
    this.http.request<Ok, RevokeKeyError>({
      path: `/dashboard/api/mcp/keys/${keyId}`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
}
