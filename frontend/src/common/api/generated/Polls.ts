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
  ClosePollError,
  ClosePollParams,
  ListPollsError,
  Poll,
} from "./data-contracts";
import { HttpClient, type RequestParams } from "./http-client";

export class Polls<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Polls
   * @name ClosePoll
   * @summary Close a poll, as the Close button in Slack does. Its creator or a Polls admin.
   * @request POST:/dashboard/api/polls/{poll_id}/close
   * @secure
   */
  closePoll = ({ pollId }: ClosePollParams, params: RequestParams = {}) =>
    this.http.request<Poll, ClosePollError>({
      path: `/dashboard/api/polls/${pollId}/close`,
      method: "POST",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Polls
   * @name ListPolls
   * @request GET:/dashboard/api/polls
   * @secure
   */
  listPolls = (params: RequestParams = {}) =>
    this.http.request<Poll[], ListPollsError>({
      path: `/dashboard/api/polls`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
}
