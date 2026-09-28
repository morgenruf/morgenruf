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
  GetMyProfileError,
  ImportProfilesError,
  ListProfilesError,
  MemberProfile,
  MemberProfileRecord,
  ProfileImportInput,
  ProfileImportResult,
  UpdateMyProfileError,
  UpdateProfileError,
  UpdateProfileParams,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Profile<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Profile
   * @name GetMyProfile
   * @request GET:/dashboard/api/profile
   * @secure
   */
  getMyProfile = (params: RequestParams = {}) =>
    this.http.request<MemberProfileRecord, GetMyProfileError>({
      path: `/dashboard/api/profile`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * @description Preview (the default) reports what would happen and writes nothing. A birthday given as a full date has its year dropped before anything else sees it. A profile the person wrote themselves is kept unless `overwrite`.
   *
   * @tags Profile
   * @name ImportProfiles
   * @summary Birthdays and start dates from `email,birthday,start_date`.
   * @request POST:/dashboard/api/profiles/import
   * @secure
   */
  importProfiles = (data: ProfileImportInput, params: RequestParams = {}) =>
    this.http.request<ProfileImportResult, ImportProfilesError>({
      path: `/dashboard/api/profiles/import`,
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
   * @tags Profile
   * @name ListProfiles
   * @request GET:/dashboard/api/profiles
   * @secure
   */
  listProfiles = (params: RequestParams = {}) =>
    this.http.request<MemberProfileRecord[], ListProfilesError>({
      path: `/dashboard/api/profiles`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Profile
   * @name UpdateMyProfile
   * @request PUT:/dashboard/api/profile
   * @secure
   */
  updateMyProfile = (data: MemberProfile, params: RequestParams = {}) =>
    this.http.request<MemberProfileRecord, UpdateMyProfileError>({
      path: `/dashboard/api/profile`,
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
   * @tags Profile
   * @name UpdateProfile
   * @request PUT:/dashboard/api/profiles/{user_id}
   * @secure
   */
  updateProfile = (
    { userId }: UpdateProfileParams,
    data: MemberProfile,
    params: RequestParams = {},
  ) =>
    this.http.request<MemberProfileRecord, UpdateProfileError>({
      path: `/dashboard/api/profiles/${userId}`,
      method: "PUT",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
