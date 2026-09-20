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
  GrantModuleAdminError,
  GrantModuleAdminParams,
  InviteMemberError,
  InviteMemberInput,
  ListMembersError,
  ListMembersParams,
  Member,
  MemberRole,
  ModuleGrant,
  RevokeModuleAdminError,
  RevokeModuleAdminParams,
  RoleInput,
  UpdateMemberRoleError,
  UpdateMemberRoleParams,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Members<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Members
   * @name GrantModuleAdmin
   * @request PUT:/dashboard/api/members/{user_id}/modules/{module}
   * @secure
   */
  grantModuleAdmin = (
    { userId, module }: GrantModuleAdminParams,
    params: RequestParams = {},
  ) =>
    this.http.request<ModuleGrant, GrantModuleAdminError>({
      path: `/dashboard/api/members/${userId}/modules/${module}`,
      method: "PUT",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Members
   * @name InviteMember
   * @summary Look up a Slack user by name/email and grant them admin role.
   * @request POST:/dashboard/api/members/invite
   * @secure
   */
  inviteMember = (data: InviteMemberInput, params: RequestParams = {}) =>
    this.http.request<MemberRole, InviteMemberError>({
      path: `/dashboard/api/members/invite`,
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
   * @tags Members
   * @name ListMembers
   * @request GET:/dashboard/api/members
   * @secure
   */
  listMembers = (query: ListMembersParams = {}, params: RequestParams = {}) =>
    this.http.request<Member[], ListMembersError>({
      path: `/dashboard/api/members`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Members
   * @name RevokeModuleAdmin
   * @request DELETE:/dashboard/api/members/{user_id}/modules/{module}
   * @secure
   */
  revokeModuleAdmin = (
    { userId, module }: RevokeModuleAdminParams,
    params: RequestParams = {},
  ) =>
    this.http.request<ModuleGrant, RevokeModuleAdminError>({
      path: `/dashboard/api/members/${userId}/modules/${module}`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Members
   * @name UpdateMemberRole
   * @request PUT:/dashboard/api/members/{user_id}/role
   * @secure
   */
  updateMemberRole = (
    { userId }: UpdateMemberRoleParams,
    data: RoleInput,
    params: RequestParams = {},
  ) =>
    this.http.request<MemberRole, UpdateMemberRoleError>({
      path: `/dashboard/api/members/${userId}/role`,
      method: "PUT",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
