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

import type { GetFeedError, GetFeedParams, PublicFeed } from "./data-contracts";
import { HttpClient, type RequestParams } from "./http-client";

export class Public<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Public
   * @name GetFeed
   * @request GET:/api/public/feed/{token}
   */
  getFeed = ({ token }: GetFeedParams, params: RequestParams = {}) =>
    this.http.request<PublicFeed, GetFeedError>({
      path: `/api/public/feed/${token}`,
      method: "GET",
      format: "json",
      ...params,
    });
}
