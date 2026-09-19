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
  ConnectMatch,
  ConnectMember,
  ConnectMemberInput,
  ConnectMemberState,
  ConnectParticipation,
  ConnectProgram,
  ConnectRound,
  ConnectRunStarted,
  CreateProgramError,
  DeleteProgramError,
  DeleteProgramParams,
  DeletedProgram,
  GetZoomError,
  ListMatchesError,
  ListMatchesParams,
  ListParticipationError,
  ListParticipationParams,
  ListProgramMembersError,
  ListProgramMembersParams,
  ListProgramsError,
  ListRoundsError,
  ListRoundsParams,
  ProgramInput,
  RunProgramError,
  RunProgramParams,
  UpdateProgramError,
  UpdateProgramMemberError,
  UpdateProgramMemberParams,
  UpdateProgramParams,
  ZoomSummary,
} from "./data-contracts";
import { ContentType, HttpClient, type RequestParams } from "./http-client";

export class Connect<SecurityDataType = unknown> {
  http: HttpClient<SecurityDataType>;

  constructor(http: HttpClient<SecurityDataType>) {
    this.http = http;
  }

  /**
   * No description
   *
   * @tags Connect
   * @name CreateProgram
   * @request POST:/dashboard/api/connect/programs
   * @secure
   */
  createProgram = (data: ProgramInput, params: RequestParams = {}) =>
    this.http.request<ConnectProgram, CreateProgramError>({
      path: `/dashboard/api/connect/programs`,
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
   * @tags Connect
   * @name DeleteProgram
   * @request DELETE:/dashboard/api/connect/programs/{program_id}
   * @secure
   */
  deleteProgram = (
    { programId }: DeleteProgramParams,
    params: RequestParams = {},
  ) =>
    this.http.request<DeletedProgram, DeleteProgramError>({
      path: `/dashboard/api/connect/programs/${programId}`,
      method: "DELETE",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * @description `configured` is what lets the page say "not set up on this deployment" rather than "nobody has connected", which are different problems with different fixes.
   *
   * @tags Connect
   * @name GetZoom
   * @summary Whether Zoom is available here, and how many people have connected.
   * @request GET:/dashboard/api/connect/zoom
   * @secure
   */
  getZoom = (params: RequestParams = {}) =>
    this.http.request<ZoomSummary, GetZoomError>({
      path: `/dashboard/api/connect/zoom`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Connect
   * @name ListMatches
   * @summary Who was put with whom, and whether it happened.
   * @request GET:/dashboard/api/connect/rounds/{round_id}/matches
   * @secure
   */
  listMatches = ({ roundId }: ListMatchesParams, params: RequestParams = {}) =>
    this.http.request<ConnectMatch[], ListMatchesError>({
      path: `/dashboard/api/connect/rounds/${roundId}/matches`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Connect
   * @name ListParticipation
   * @request GET:/dashboard/api/connect/programs/{program_id}/participation
   * @secure
   */
  listParticipation = (
    { programId, ...query }: ListParticipationParams,
    params: RequestParams = {},
  ) =>
    this.http.request<ConnectParticipation[], ListParticipationError>({
      path: `/dashboard/api/connect/programs/${programId}/participation`,
      method: "GET",
      query: query,
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * @description There was no way to see or change this from the dashboard at all: the opt-out table has existed since the module shipped and only the person themselves could write to it, from Slack. An admin could not tell who had quietly excluded themselves, let alone put somebody back in.
   *
   * @tags Connect
   * @name ListProgramMembers
   * @summary Who is in this programme and how each of them stands.
   * @request GET:/dashboard/api/connect/programs/{program_id}/members
   * @secure
   */
  listProgramMembers = (
    { programId }: ListProgramMembersParams,
    params: RequestParams = {},
  ) =>
    this.http.request<ConnectMember[], ListProgramMembersError>({
      path: `/dashboard/api/connect/programs/${programId}/members`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Connect
   * @name ListPrograms
   * @request GET:/dashboard/api/connect/programs
   * @secure
   */
  listPrograms = (params: RequestParams = {}) =>
    this.http.request<ConnectProgram[], ListProgramsError>({
      path: `/dashboard/api/connect/programs`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Connect
   * @name ListRounds
   * @request GET:/dashboard/api/connect/programs/{program_id}/rounds
   * @secure
   */
  listRounds = ({ programId }: ListRoundsParams, params: RequestParams = {}) =>
    this.http.request<ConnectRound[], ListRoundsError>({
      path: `/dashboard/api/connect/programs/${programId}/rounds`,
      method: "GET",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * @description Without this a programme could not be tried at all until its scheduled day came round, which is a poor way to find out whether it works.
   *
   * @tags Connect
   * @name RunProgram
   * @summary Start a round immediately, rather than waiting for the cadence.
   * @request POST:/dashboard/api/connect/programs/{program_id}/run
   * @secure
   */
  runProgram = ({ programId }: RunProgramParams, params: RequestParams = {}) =>
    this.http.request<ConnectRunStarted, RunProgramError>({
      path: `/dashboard/api/connect/programs/${programId}/run`,
      method: "POST",
      secure: true,
      format: "json",
      ...params,
    });
  /**
   * No description
   *
   * @tags Connect
   * @name UpdateProgram
   * @summary Change a programme. A body with only `enabled` keeps the old toggle behaviour, so the switch on the card still works unchanged.
   * @request POST:/dashboard/api/connect/programs/{program_id}
   * @secure
   */
  updateProgram = (
    { programId }: UpdateProgramParams,
    data: ProgramInput,
    params: RequestParams = {},
  ) =>
    this.http.request<ConnectProgram, UpdateProgramError>({
      path: `/dashboard/api/connect/programs/${programId}`,
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
   * @tags Connect
   * @name UpdateProgramMember
   * @summary Put somebody in, take them out, or snooze them until a date.
   * @request POST:/dashboard/api/connect/programs/{program_id}/members/{user_id}
   * @secure
   */
  updateProgramMember = (
    { programId, userId }: UpdateProgramMemberParams,
    data: ConnectMemberInput,
    params: RequestParams = {},
  ) =>
    this.http.request<ConnectMemberState, UpdateProgramMemberError>({
      path: `/dashboard/api/connect/programs/${programId}/members/${userId}`,
      method: "POST",
      body: data,
      secure: true,
      type: ContentType.Json,
      format: "json",
      ...params,
    });
}
