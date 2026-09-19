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
  CreateWebhookError,
  DeleteWebhookError,
  DeleteWebhookParams,
  GetWebhookEventsError,
  ListWebhookDeliveriesError,
  ListWebhookDeliveriesParams,
  ListWebhooksError,
  Ok,
  RotateWebhookSecretError,
  RotateWebhookSecretParams,
  TestWebhookError,
  TestWebhookParams,
  UpdateWebhookError,
  UpdateWebhookParams,
  Webhook,
  WebhookDelivery,
  WebhookEvents,
  WebhookInput,
  WebhookTest,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Webhooks<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Webhooks
   * @name CreateWebhook
   * @request POST:/dashboard/api/webhooks
   * @secure
   */
  createWebhook = (data: WebhookInput, params: RequestParams = {}) =>
    this.http.request<Webhook, CreateWebhookError>({
      path: `/dashboard/api/webhooks`,
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
   * @tags Webhooks
   * @name DeleteWebhook
   * @request DELETE:/dashboard/api/webhooks/{hook_id}
   * @secure
   */
  deleteWebhook = (
    { hookId }: DeleteWebhookParams,
    params: RequestParams = {},
  ) =>
    this.http.request<Ok, DeleteWebhookError>({
      path: `/dashboard/api/webhooks/${hookId}`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Webhooks
   * @name GetWebhookEvents
   * @summary List the event names a webhook can subscribe to.
   * @request GET:/dashboard/api/webhooks/events
   * @secure
   */
  getWebhookEvents = (params: RequestParams = {}) =>
    this.http.request<WebhookEvents, GetWebhookEventsError>({
      path: `/dashboard/api/webhooks/events`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Webhooks
   * @name ListWebhookDeliveries
   * @summary Recent delivery attempts, newest first, for the team or one webhook.
   * @request GET:/dashboard/api/webhooks/{hook_id}/deliveries
   * @secure
   */
  listWebhookDeliveries = (
    { hookId, ...query }: ListWebhookDeliveriesParams,
    params: RequestParams = {},
  ) =>
    this.http.request<WebhookDelivery[], ListWebhookDeliveriesError>({
      path: `/dashboard/api/webhooks/${hookId}/deliveries`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Webhooks
   * @name ListWebhooks
   * @request GET:/dashboard/api/webhooks
   * @secure
   */
  listWebhooks = (params: RequestParams = {}) =>
    this.http.request<Webhook[], ListWebhooksError>({
      path: `/dashboard/api/webhooks`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * @description Rotating is also how a pre-signing webhook adopts signing: those rows keep a NULL secret and deliver unsigned until an operator rotates deliberately, because turning on signatures behind the receiver's back would break a strict verifier that has never been given a key.
   *
   * @tags Webhooks
   * @name RotateWebhookSecret
   * @summary Issue a new signing secret and return it once.
   * @request POST:/dashboard/api/webhooks/{hook_id}/rotate
   * @secure
   */
  rotateWebhookSecret = (
    { hookId }: RotateWebhookSecretParams,
    params: RequestParams = {},
  ) =>
    this.http.request<Webhook, RotateWebhookSecretError>({
      path: `/dashboard/api/webhooks/${hookId}/rotate`,
      method: "POST",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Webhooks
   * @name TestWebhook
   * @summary Send a synthetic event through the real signing and logging path.
   * @request POST:/dashboard/api/webhooks/{hook_id}/test
   * @secure
   */
  testWebhook = ({ hookId }: TestWebhookParams, params: RequestParams = {}) =>
    this.http.request<WebhookTest, TestWebhookError>({
      path: `/dashboard/api/webhooks/${hookId}/test`,
      method: "POST",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Webhooks
   * @name UpdateWebhook
   * @summary Update a webhook's URL and/or its event subscription.
   * @request PATCH:/dashboard/api/webhooks/{hook_id}
   * @secure
   */
  updateWebhook = (
    { hookId }: UpdateWebhookParams,
    data: WebhookInput,
    params: RequestParams = {},
  ) =>
    this.http.request<Webhook, UpdateWebhookError>({
      path: `/dashboard/api/webhooks/${hookId}`,
      method: "PATCH",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
