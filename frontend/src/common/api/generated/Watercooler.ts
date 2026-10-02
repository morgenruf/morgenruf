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
  AddWatercoolerQuestionError,
  DeleteWatercoolerChannelError,
  DeleteWatercoolerChannelParams,
  GetWatercoolerError,
  Ok,
  PostWatercoolerNowError,
  PostWatercoolerNowParams,
  SaveWatercoolerChannelError,
  SaveWatercoolerChannelParams,
  SetWatercoolerHiddenError,
  SetWatercoolerHiddenParams,
  UpdateWatercoolerQuestionError,
  UpdateWatercoolerQuestionParams,
  WatercoolerBankQuestion,
  WatercoolerChannel,
  WatercoolerChannelInput,
  WatercoolerHiddenInput,
  WatercoolerOverview,
  WatercoolerPostResult,
  WatercoolerQuestion,
  WatercoolerQuestionInput,
  WatercoolerQuestionUpdate,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Watercooler<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Watercooler
   * @name AddWatercoolerQuestion
   * @request POST:/dashboard/api/watercooler/questions
   * @secure
   */
  addWatercoolerQuestion = (
    data: WatercoolerQuestionInput,
    params: RequestParams = {},
  ) =>
    this.http.request<WatercoolerQuestion, AddWatercoolerQuestionError>({
      path: `/dashboard/api/watercooler/questions`,
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
   * @tags Watercooler
   * @name DeleteWatercoolerChannel
   * @request DELETE:/dashboard/api/watercooler/channels/{channel_id}
   * @secure
   */
  deleteWatercoolerChannel = (
    { channelId }: DeleteWatercoolerChannelParams,
    params: RequestParams = {},
  ) =>
    this.http.request<Ok, DeleteWatercoolerChannelError>({
      path: `/dashboard/api/watercooler/channels/${channelId}`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Watercooler
   * @name GetWatercooler
   * @request GET:/dashboard/api/watercooler
   * @secure
   */
  getWatercooler = (params: RequestParams = {}) =>
    this.http.request<WatercoolerOverview, GetWatercoolerError>({
      path: `/dashboard/api/watercooler`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Watercooler
   * @name PostWatercoolerNow
   * @summary Post today's question now. It counts as today's post, so the scheduled one is skipped.
   * @request POST:/dashboard/api/watercooler/channels/{channel_id}/post
   * @secure
   */
  postWatercoolerNow = (
    { channelId }: PostWatercoolerNowParams,
    params: RequestParams = {},
  ) =>
    this.http.request<WatercoolerPostResult, PostWatercoolerNowError>({
      path: `/dashboard/api/watercooler/channels/${channelId}/post`,
      method: "POST",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Watercooler
   * @name SaveWatercoolerChannel
   * @request PUT:/dashboard/api/watercooler/channels/{channel_id}
   * @secure
   */
  saveWatercoolerChannel = (
    { channelId }: SaveWatercoolerChannelParams,
    data: WatercoolerChannelInput,
    params: RequestParams = {},
  ) =>
    this.http.request<WatercoolerChannel, SaveWatercoolerChannelError>({
      path: `/dashboard/api/watercooler/channels/${channelId}`,
      method: "PUT",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Watercooler
   * @name SetWatercoolerHidden
   * @request PUT:/dashboard/api/watercooler/bank/{key}
   * @secure
   */
  setWatercoolerHidden = (
    { key }: SetWatercoolerHiddenParams,
    data: WatercoolerHiddenInput,
    params: RequestParams = {},
  ) =>
    this.http.request<WatercoolerBankQuestion, SetWatercoolerHiddenError>({
      path: `/dashboard/api/watercooler/bank/${key}`,
      method: "PUT",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Watercooler
   * @name UpdateWatercoolerQuestion
   * @request PATCH:/dashboard/api/watercooler/questions/{question_id}
   * @secure
   */
  updateWatercoolerQuestion = (
    { questionId }: UpdateWatercoolerQuestionParams,
    data: WatercoolerQuestionUpdate,
    params: RequestParams = {},
  ) =>
    this.http.request<WatercoolerQuestion, UpdateWatercoolerQuestionError>({
      path: `/dashboard/api/watercooler/questions/${questionId}`,
      method: "PATCH",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
