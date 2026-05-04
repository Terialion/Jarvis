# Codex 关键参考代码摘录

### run_turn 入口与 pre-sampling compact

Source: `codex/codex-main/codex-rs/core/src/session/turn.rs` lines 136-220

```
0136: pub(crate) async fn run_turn(
0137:     sess: Arc<Session>,
0138:     turn_context: Arc<TurnContext>,
0139:     input: Vec<UserInput>,
0140:     prewarmed_client_session: Option<ModelClientSession>,
0141:     cancellation_token: CancellationToken,
0142: ) -> Option<String> {
0143:     if input.is_empty() && !sess.has_pending_input().await {
0144:         return None;
0145:     }
0146: 
0147:     let model_info = turn_context.model_info.clone();
0148:     let auto_compact_limit = model_info.auto_compact_token_limit().unwrap_or(i64::MAX);
0149:     let mut prewarmed_client_session = prewarmed_client_session;
0150:     // TODO(ccunningham): Pre-turn compaction runs before context updates and the
0151:     // new user message are recorded. Estimate pending incoming items (context
0152:     // diffs/full reinjection + user input) and trigger compaction preemptively
0153:     // when they would push the thread over the compaction threshold.
0154:     let pre_sampling_compacted = match run_pre_sampling_compact(&sess, &turn_context).await {
0155:         Ok(pre_sampling_compacted) => pre_sampling_compacted,
0156:         Err(_) => {
0157:             error!("Failed to run pre-sampling compact");
0158:             return None;
0159:         }
0160:     };
0161:     if pre_sampling_compacted && let Some(mut client_session) = prewarmed_client_session.take() {
0162:         client_session.reset_websocket_session();
0163:     }
0164: 
0165:     let skills_outcome = Some(turn_context.turn_skills.outcome.as_ref());
0166: 
0167:     sess.record_context_updates_and_set_reference_context_item(turn_context.as_ref())
0168:         .await;
0169: 
0170:     let loaded_plugins = sess
0171:         .services
0172:         .plugins_manager
0173:         .plugins_for_config(&turn_context.config)
0174:         .await;
0175:     // Structured plugin:// mentions are resolved from the current session's
0176:     // enabled plugins, then converted into turn-scoped guidance below.
0177:     let mentioned_plugins =
0178:         collect_explicit_plugin_mentions(&input, loaded_plugins.capability_summaries());
0179:     let mcp_tools = if turn_context.apps_enabled() || !mentioned_plugins.is_empty() {
0180:         // Plugin mentions need raw MCP/app inventory even when app tools
0181:         // are normally hidden so we can describe the plugin's currently
0182:         // usable capabilities for this turn.
0183:         match sess
0184:             .services
0185:             .mcp_connection_manager
0186:             .read()
0187:             .await
0188:             .list_all_tools()
0189:             .or_cancel(&cancellation_token)
0190:             .await
0191:         {
0192:             Ok(mcp_tools) => mcp_tools,
0193:             Err(_) if turn_context.apps_enabled() => return None,
0194:             Err(_) => HashMap::new(),
0195:         }
0196:     } else {
0197:         HashMap::new()
0198:     };
0199:     let available_connectors = if turn_context.apps_enabled() {
0200:         let connectors = codex_connectors::merge::merge_plugin_connectors_with_accessible(
0201:             loaded_plugins
0202:                 .effective_apps()
0203:                 .into_iter()
0204:                 .map(|connector_id| connector_id.0),
0205:             connectors::accessible_connectors_from_mcp_tools(&mcp_tools),
0206:         );
0207:         connectors::with_app_enabled_state(connectors, &turn_context.config)
0208:     } else {
0209:         Vec::new()
0210:     };
0211:     let connector_slug_counts = build_connector_slug_counts(&available_connectors);
0212:     let skill_name_counts_lower = skills_outcome
0213:         .as_ref()
0214:         .map_or_else(HashMap::new, |outcome| {
0215:             build_skill_name_counts(&outcome.skills, &outcome.disabled_paths).1
0216:         });
0217:     let mentioned_skills = skills_outcome.as_ref().map_or_else(Vec::new, |outcome| {
0218:         collect_explicit_skill_mentions(
0219:             &input,
0220:             &outcome.skills,
```
### sampling loop 与 auto compact 触发区

Source: `codex/codex-main/codex-rs/core/src/session/turn.rs` lines 430-535

```
0430:         let sampling_request_input: Vec<ResponseItem> = {
0431:             sess.clone_history()
0432:                 .await
0433:                 .for_prompt(&turn_context.model_info.input_modalities)
0434:         };
0435: 
0436:         let sampling_request_input_messages = sampling_request_input
0437:             .iter()
0438:             .filter_map(|item| match parse_turn_item(item) {
0439:                 Some(TurnItem::UserMessage(user_message)) => Some(user_message),
0440:                 _ => None,
0441:             })
0442:             .map(|user_message| user_message.message())
0443:             .collect::<Vec<String>>();
0444:         let turn_metadata_header = turn_context.turn_metadata_state.current_header_value();
0445:         match run_sampling_request(
0446:             Arc::clone(&sess),
0447:             Arc::clone(&turn_context),
0448:             Arc::clone(&turn_diff_tracker),
0449:             &mut client_session,
0450:             turn_metadata_header.as_deref(),
0451:             sampling_request_input,
0452:             &explicitly_enabled_connectors,
0453:             skills_outcome,
0454:             cancellation_token.child_token(),
0455:         )
0456:         .await
0457:         {
0458:             Ok(sampling_request_output) => {
0459:                 let SamplingRequestResult {
0460:                     needs_follow_up: model_needs_follow_up,
0461:                     last_agent_message: sampling_request_last_agent_message,
0462:                 } = sampling_request_output;
0463:                 can_drain_pending_input = true;
0464:                 let has_pending_input = sess.has_pending_input().await;
0465:                 let needs_follow_up = model_needs_follow_up || has_pending_input;
0466:                 let total_usage_tokens = sess.get_total_token_usage().await;
0467:                 let token_limit_reached = total_usage_tokens >= auto_compact_limit;
0468: 
0469:                 let estimated_token_count =
0470:                     sess.get_estimated_token_count(turn_context.as_ref()).await;
0471: 
0472:                 trace!(
0473:                     turn_id = %turn_context.sub_id,
0474:                     total_usage_tokens,
0475:                     estimated_token_count = ?estimated_token_count,
0476:                     auto_compact_limit,
0477:                     token_limit_reached,
0478:                     model_needs_follow_up,
0479:                     has_pending_input,
0480:                     needs_follow_up,
0481:                     "post sampling token usage"
0482:                 );
0483: 
0484:                 // as long as compaction works well in getting us way below the token limit, we shouldn't worry about being in an infinite loop.
0485:                 if token_limit_reached && needs_follow_up {
0486:                     if run_auto_compact(
0487:                         &sess,
0488:                         &turn_context,
0489:                         InitialContextInjection::BeforeLastUserMessage,
0490:                         CompactionReason::ContextLimit,
0491:                         CompactionPhase::MidTurn,
0492:                     )
0493:                     .await
0494:                     .is_err()
0495:                     {
0496:                         return None;
0497:                     }
0498:                     client_session.reset_websocket_session();
0499:                     can_drain_pending_input = !model_needs_follow_up;
0500:                     continue;
0501:                 }
0502: 
0503:                 if !needs_follow_up {
0504:                     last_agent_message = sampling_request_last_agent_message;
0505:                     let stop_hook_permission_mode = match turn_context.approval_policy.value() {
0506:                         AskForApproval::Never => "bypassPermissions",
0507:                         AskForApproval::UnlessTrusted
0508:                         | AskForApproval::OnFailure
0509:                         | AskForApproval::OnRequest
0510:                         | AskForApproval::Granular(_) => "default",
0511:                     }
0512:                     .to_string();
0513:                     let stop_request = codex_hooks::StopRequest {
0514:                         session_id: sess.conversation_id,
0515:                         turn_id: turn_context.sub_id.clone(),
0516:                         cwd: turn_context.cwd.clone(),
0517:                         transcript_path: sess.hook_transcript_path().await,
0518:                         model: turn_context.model_info.slug.clone(),
0519:                         permission_mode: stop_hook_permission_mode,
0520:                         stop_hook_active,
0521:                         last_assistant_message: last_agent_message.clone(),
0522:                     };
0523:                     let hooks = sess.hooks();
0524:                     for run in hooks.preview_stop(&stop_request) {
0525:                         sess.send_event(
0526:                             &turn_context,
0527:                             EventMsg::HookStarted(codex_protocol::protocol::HookStartedEvent {
0528:                                 turn_id: Some(turn_context.sub_id.clone()),
0529:                                 run,
0530:                             }),
0531:                         )
0532:                         .await;
0533:                     }
0534:                     let stop_outcome = hooks.run_stop(stop_request).await;
0535:                     emit_hook_completed_events(&sess, &turn_context, stop_outcome.hook_events)
```
### TurnContext 状态集中管理

Source: `codex/codex-main/codex-rs/core/src/session/turn_context.rs` lines 50-115

```
0050: pub(crate) struct TurnContext {
0051:     pub(crate) sub_id: String,
0052:     pub(crate) trace_id: Option<String>,
0053:     pub(crate) realtime_active: bool,
0054:     pub(crate) config: Arc<Config>,
0055:     pub(crate) auth_manager: Option<Arc<AuthManager>>,
0056:     pub(crate) model_info: ModelInfo,
0057:     pub(crate) session_telemetry: SessionTelemetry,
0058:     pub(crate) provider: SharedModelProvider,
0059:     pub(crate) reasoning_effort: Option<ReasoningEffortConfig>,
0060:     pub(crate) reasoning_summary: ReasoningSummaryConfig,
0061:     pub(crate) session_source: SessionSource,
0062:     pub(crate) environment: Option<Arc<Environment>>,
0063:     pub(crate) environments: Vec<TurnEnvironment>,
0064:     /// The session's absolute working directory. All relative paths provided
0065:     /// by the model as well as sandbox policies are resolved against this path
0066:     /// instead of `std::env::current_dir()`.
0067:     pub(crate) cwd: AbsolutePathBuf,
0068:     pub(crate) current_date: Option<String>,
0069:     pub(crate) timezone: Option<String>,
0070:     pub(crate) app_server_client_name: Option<String>,
0071:     pub(crate) developer_instructions: Option<String>,
0072:     pub(crate) compact_prompt: Option<String>,
0073:     pub(crate) user_instructions: Option<String>,
0074:     pub(crate) collaboration_mode: CollaborationMode,
0075:     pub(crate) personality: Option<Personality>,
0076:     pub(crate) approval_policy: Constrained<AskForApproval>,
0077:     pub(crate) permission_profile: PermissionProfile,
0078:     pub(crate) network: Option<NetworkProxy>,
0079:     pub(crate) windows_sandbox_level: WindowsSandboxLevel,
0080:     pub(crate) shell_environment_policy: ShellEnvironmentPolicy,
0081:     pub(crate) tools_config: ToolsConfig,
0082:     pub(crate) features: ManagedFeatures,
0083:     pub(crate) ghost_snapshot: GhostSnapshotConfig,
0084:     pub(crate) final_output_json_schema: Option<Value>,
0085:     pub(crate) codex_self_exe: Option<PathBuf>,
0086:     pub(crate) codex_linux_sandbox_exe: Option<PathBuf>,
0087:     pub(crate) tool_call_gate: Arc<ReadinessFlag>,
0088:     pub(crate) truncation_policy: TruncationPolicy,
0089:     pub(crate) dynamic_tools: Vec<DynamicToolSpec>,
0090:     pub(crate) turn_metadata_state: Arc<TurnMetadataState>,
0091:     pub(crate) turn_skills: TurnSkillsContext,
0092:     pub(crate) turn_timing_state: Arc<TurnTimingState>,
0093:     pub(crate) server_model_warning_emitted: AtomicBool,
0094:     pub(crate) model_verification_emitted: AtomicBool,
0095: }
0096: impl TurnContext {
0097:     pub(crate) fn permission_profile(&self) -> PermissionProfile {
0098:         self.permission_profile.clone()
0099:     }
0100: 
0101:     pub(crate) fn file_system_sandbox_policy(&self) -> FileSystemSandboxPolicy {
0102:         self.permission_profile.file_system_sandbox_policy()
0103:     }
0104: 
0105:     pub(crate) fn network_sandbox_policy(&self) -> NetworkSandboxPolicy {
0106:         self.permission_profile.network_sandbox_policy()
0107:     }
0108: 
0109:     pub(crate) fn sandbox_policy(&self) -> SandboxPolicy {
0110:         let file_system_sandbox_policy = self.file_system_sandbox_policy();
0111:         let network_sandbox_policy = self.network_sandbox_policy();
0112:         compatibility_sandbox_policy_for_permission_profile(
0113:             &self.permission_profile,
0114:             &file_system_sandbox_policy,
0115:             network_sandbox_policy,
```
### MCP tool call handler 入口

Source: `codex/codex-main/codex-rs/core/src/mcp_tool_call.rs` lines 87-135

```
0087: pub(crate) async fn handle_mcp_tool_call(
0088:     sess: Arc<Session>,
0089:     turn_context: &Arc<TurnContext>,
0090:     call_id: String,
0091:     server: String,
0092:     tool_name: String,
0093:     hook_tool_name: String,
0094:     arguments: String,
0095: ) -> HandledMcpToolCall {
0096:     // Parse the `arguments` as JSON. An empty string is OK, but invalid JSON
0097:     // is not.
0098:     let arguments_value = if arguments.trim().is_empty() {
0099:         None
0100:     } else {
0101:         match serde_json::from_str::<serde_json::Value>(&arguments) {
0102:             Ok(value) => Some(value),
0103:             Err(e) => {
0104:                 error!("failed to parse tool call arguments: {e}");
0105:                 return HandledMcpToolCall {
0106:                     result: CallToolResult::from_error_text(format!("err: {e}")),
0107:                     tool_input: JsonValue::Object(serde_json::Map::new()),
0108:                 };
0109:             }
0110:         }
0111:     };
0112: 
0113:     let invocation = McpInvocation {
0114:         server: server.clone(),
0115:         tool: tool_name.clone(),
0116:         arguments: arguments_value.clone(),
0117:     };
0118: 
0119:     let metadata =
0120:         lookup_mcp_tool_metadata(sess.as_ref(), turn_context.as_ref(), &server, &tool_name).await;
0121:     let mcp_app_resource_uri = metadata
0122:         .as_ref()
0123:         .and_then(|metadata| metadata.mcp_app_resource_uri.clone());
0124:     let app_tool_policy = if server == CODEX_APPS_MCP_SERVER_NAME {
0125:         connectors::app_tool_policy(
0126:             &turn_context.config,
0127:             metadata
0128:                 .as_ref()
0129:                 .and_then(|metadata| metadata.connector_id.as_deref()),
0130:             &tool_name,
0131:             metadata
0132:                 .as_ref()
0133:                 .and_then(|metadata| metadata.tool_title.as_deref()),
0134:             metadata
0135:                 .as_ref()
```
### approved MCP tool call 执行与 begin/end event

Source: `codex/codex-main/codex-rs/core/src/mcp_tool_call.rs` lines 291-370

```
0291: async fn handle_approved_mcp_tool_call(
0292:     sess: &Session,
0293:     turn_context: &TurnContext,
0294:     call_id: &str,
0295:     invocation: McpInvocation,
0296:     metadata: Option<&McpToolApprovalMetadata>,
0297:     request_meta: Option<JsonValue>,
0298:     mcp_app_resource_uri: Option<String>,
0299: ) -> HandledMcpToolCall {
0300:     maybe_mark_thread_memory_mode_polluted(sess, turn_context).await;
0301: 
0302:     let server = invocation.server.clone();
0303:     let tool_name = invocation.tool.clone();
0304:     let arguments_value = invocation.arguments.clone();
0305:     let connector_id = metadata.and_then(|metadata| metadata.connector_id.as_deref());
0306:     let connector_name = metadata.and_then(|metadata| metadata.connector_name.as_deref());
0307:     let server_origin = sess
0308:         .services
0309:         .mcp_connection_manager
0310:         .read()
0311:         .await
0312:         .server_origin(&server)
0313:         .map(str::to_string);
0314: 
0315:     let start = Instant::now();
0316:     let rewrite = rewrite_mcp_tool_arguments_for_openai_files(
0317:         sess,
0318:         turn_context,
0319:         arguments_value.clone(),
0320:         metadata.and_then(|metadata| metadata.openai_file_input_params.as_deref()),
0321:     )
0322:     .await;
0323:     let tool_input = match &rewrite {
0324:         Ok(Some(rewritten_arguments)) => rewritten_arguments.clone(),
0325:         Ok(None) | Err(_) => arguments_value
0326:             .clone()
0327:             .unwrap_or_else(|| JsonValue::Object(serde_json::Map::new())),
0328:     };
0329:     let result = async {
0330:         let rewritten_arguments = rewrite?;
0331:         let result = execute_mcp_tool_call(
0332:             sess,
0333:             turn_context,
0334:             &server,
0335:             &tool_name,
0336:             rewritten_arguments,
0337:             request_meta,
0338:         )
0339:         .await;
0340:         record_mcp_result_span_telemetry(&Span::current(), result.as_ref().ok());
0341:         result
0342:     }
0343:     .instrument(mcp_tool_call_span(
0344:         sess,
0345:         turn_context,
0346:         McpToolCallSpanFields {
0347:             server_name: &server,
0348:             tool_name: &tool_name,
0349:             call_id,
0350:             server_origin: server_origin.as_deref(),
0351:             connector_id,
0352:             connector_name,
0353:         },
0354:     ))
0355:     .await;
0356:     if let Err(error) = &result {
0357:         tracing::warn!("MCP tool call error: {error:?}");
0358:     }
0359:     let duration = start.elapsed();
0360:     let tool_call_end_event = EventMsg::McpToolCallEnd(McpToolCallEndEvent {
0361:         call_id: call_id.to_string(),
0362:         invocation,
0363:         mcp_app_resource_uri,
0364:         duration,
0365:         result: result.clone(),
0366:     });
0367:     notify_mcp_tool_call_event(sess, turn_context, tool_call_end_event.clone()).await;
0368:     maybe_track_codex_app_used(sess, turn_context, &server, &tool_name).await;
0369: 
0370:     let status = if result.is_ok() { "ok" } else { "error" };
```
### exec tool call 受控执行入口

Source: `codex/codex-main/codex-rs/core/src/exec.rs` lines 293-365

```
0293: pub async fn process_exec_tool_call(
0294:     params: ExecParams,
0295:     permission_profile: &PermissionProfile,
0296:     sandbox_cwd: &AbsolutePathBuf,
0297:     codex_linux_sandbox_exe: &Option<PathBuf>,
0298:     use_legacy_landlock: bool,
0299:     stdout_stream: Option<StdoutStream>,
0300: ) -> Result<ExecToolCallOutput> {
0301:     let exec_req = build_exec_request(
0302:         params,
0303:         permission_profile,
0304:         sandbox_cwd,
0305:         codex_linux_sandbox_exe,
0306:         use_legacy_landlock,
0307:     )?;
0308: 
0309:     // Route through the sandboxing module for a single, unified execution path.
0310:     crate::sandboxing::execute_env(exec_req, stdout_stream).await
0311: }
0312: 
0313: /// Transform a portable exec request into the concrete argv/env that should be
0314: /// spawned under the requested sandbox policy.
0315: pub fn build_exec_request(
0316:     params: ExecParams,
0317:     permission_profile: &PermissionProfile,
0318:     sandbox_cwd: &AbsolutePathBuf,
0319:     codex_linux_sandbox_exe: &Option<PathBuf>,
0320:     use_legacy_landlock: bool,
0321: ) -> Result<ExecRequest> {
0322:     let ExecParams {
0323:         command,
0324:         cwd,
0325:         mut env,
0326:         expiration,
0327:         capture_policy,
0328:         network,
0329:         windows_sandbox_level,
0330:         windows_sandbox_private_desktop,
0331: 
0332:         // TODO: Should arg0 be set on the ExecRequest that is returned?
0333:         arg0: _,
0334:         // These fields are related to approvals, so can be ignored here.
0335:         justification: _,
0336:         sandbox_permissions: _,
0337:     } = params;
0338: 
0339:     let enforce_managed_network = network.is_some();
0340:     let (file_system_sandbox_policy, network_sandbox_policy) =
0341:         permission_profile.to_runtime_permissions();
0342:     let sandbox_type = select_process_exec_tool_sandbox_type(
0343:         &file_system_sandbox_policy,
0344:         network_sandbox_policy,
0345:         windows_sandbox_level,
0346:         enforce_managed_network,
0347:     );
0348:     tracing::debug!("Sandbox type: {sandbox_type:?}");
0349: 
0350:     if let Some(network) = network.as_ref() {
0351:         network.apply_to_env(&mut env);
0352:     }
0353:     let (program, args) = command.split_first().ok_or_else(|| {
0354:         CodexErr::Io(io::Error::new(
0355:             io::ErrorKind::InvalidInput,
0356:             "command args are empty",
0357:         ))
0358:     })?;
0359: 
0360:     let manager = SandboxManager::new();
0361:     let command = SandboxCommand {
0362:         program: program.clone().into(),
0363:         args: args.to_vec(),
0364:         cwd,
0365:         env,
```
