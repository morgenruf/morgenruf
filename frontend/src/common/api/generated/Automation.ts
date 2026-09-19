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
  AutomationRule,
  AutomationRuleInput,
  CreateRuleError,
  CreatedId,
  DeleteRuleError,
  DeleteRuleParams,
  ListRulesError,
  Ok,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Automation<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Automation
   * @name CreateRule
   * @request POST:/dashboard/api/rules
   * @secure
   */
  createRule = (data: AutomationRuleInput, params: RequestParams = {}) =>
    this.http.request<CreatedId, CreateRuleError>({
      path: `/dashboard/api/rules`,
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
   * @tags Automation
   * @name DeleteRule
   * @request DELETE:/dashboard/api/rules/{rule_id}
   * @secure
   */
  deleteRule = ({ ruleId }: DeleteRuleParams, params: RequestParams = {}) =>
    this.http.request<Ok, DeleteRuleError>({
      path: `/dashboard/api/rules/${ruleId}`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Automation
   * @name ListRules
   * @request GET:/dashboard/api/rules
   * @secure
   */
  listRules = (params: RequestParams = {}) =>
    this.http.request<AutomationRule[], ListRulesError>({
      path: `/dashboard/api/rules`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
}
