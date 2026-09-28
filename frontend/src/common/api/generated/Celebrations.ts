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
  AddHolidayError,
  AskForDatesError,
  AskForDatesPreview,
  AskForDatesResult,
  CelebrationSettings,
  DeleteHolidayError,
  DeleteHolidayParams,
  GetCelebrationSettingsError,
  Holiday,
  HolidayImportInput,
  HolidayImportResult,
  HolidayInput,
  ImportHolidaysError,
  ListHolidaysError,
  ListUpcomingCelebrationsError,
  PreviewAskForDatesError,
  SettingsInput,
  UpcomingCelebration,
  UpdateCelebrationSettingsError,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Celebrations<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Celebrations
   * @name AddHoliday
   * @summary Add one holiday, or rename the one already on that date. Returns the list.
   * @request POST:/dashboard/api/celebrations/holidays
   * @secure
   */
  addHoliday = (data: HolidayInput, params: RequestParams = {}) =>
    this.http.request<Holiday[], AddHolidayError>({
      path: `/dashboard/api/celebrations/holidays`,
      method: "POST",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
  /**
   * @description The people are claimed before anything is sent, so a double click or a second admin sends nothing more. The DMs go out in the background.
   *
   * @tags Celebrations
   * @name AskForDates
   * @summary DM everyone still missing dates, at most once per person per 30 days.
   * @request POST:/dashboard/api/celebrations/ask-dates
   * @secure
   */
  askForDates = (params: RequestParams = {}) =>
    this.http.request<AskForDatesResult, AskForDatesError>({
      path: `/dashboard/api/celebrations/ask-dates`,
      method: "POST",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Celebrations
   * @name DeleteHoliday
   * @request DELETE:/dashboard/api/celebrations/holidays/{day}
   * @secure
   */
  deleteHoliday = ({ day }: DeleteHolidayParams, params: RequestParams = {}) =>
    this.http.request<Holiday[], DeleteHolidayError>({
      path: `/dashboard/api/celebrations/holidays/${day}`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Celebrations
   * @name GetCelebrationSettings
   * @request GET:/dashboard/api/celebrations/settings
   * @secure
   */
  getCelebrationSettings = (params: RequestParams = {}) =>
    this.http.request<CelebrationSettings, GetCelebrationSettingsError>({
      path: `/dashboard/api/celebrations/settings`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Celebrations
   * @name ImportHolidays
   * @summary Holidays from `date,name` lines. Preview (the default) writes nothing.
   * @request POST:/dashboard/api/celebrations/holidays/import
   * @secure
   */
  importHolidays = (data: HolidayImportInput, params: RequestParams = {}) =>
    this.http.request<HolidayImportResult, ImportHolidaysError>({
      path: `/dashboard/api/celebrations/holidays/import`,
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
   * @tags Celebrations
   * @name ListHolidays
   * @request GET:/dashboard/api/celebrations/holidays
   * @secure
   */
  listHolidays = (params: RequestParams = {}) =>
    this.http.request<Holiday[], ListHolidaysError>({
      path: `/dashboard/api/celebrations/holidays`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Celebrations
   * @name ListUpcomingCelebrations
   * @summary What the next 30 days will post, and on which day. Admins only: it lists birthdays.
   * @request GET:/dashboard/api/celebrations/upcoming
   * @secure
   */
  listUpcomingCelebrations = (params: RequestParams = {}) =>
    this.http.request<UpcomingCelebration[], ListUpcomingCelebrationsError>({
      path: `/dashboard/api/celebrations/upcoming`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Celebrations
   * @name PreviewAskForDates
   * @summary How many people would be asked, and the message they would get. Sends nothing.
   * @request GET:/dashboard/api/celebrations/ask-dates
   * @secure
   */
  previewAskForDates = (params: RequestParams = {}) =>
    this.http.request<AskForDatesPreview, PreviewAskForDatesError>({
      path: `/dashboard/api/celebrations/ask-dates`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Celebrations
   * @name UpdateCelebrationSettings
   * @request PUT:/dashboard/api/celebrations/settings
   * @secure
   */
  updateCelebrationSettings = (
    data: SettingsInput,
    params: RequestParams = {},
  ) =>
    this.http.request<CelebrationSettings, UpdateCelebrationSettingsError>({
      path: `/dashboard/api/celebrations/settings`,
      method: "PUT",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
