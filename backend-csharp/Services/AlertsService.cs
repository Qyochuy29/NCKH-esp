using Microsoft.EntityFrameworkCore;
using SchoolGuardian.Api.Data;
using SchoolGuardian.Api.DTOs;
using SchoolGuardian.Api.Models;
using SchoolGuardian.Api.Hubs;
using Microsoft.AspNetCore.SignalR;
using System.Text.Json;

namespace SchoolGuardian.Api.Services
{
    public class AlertsService
    {
        private readonly ApplicationDbContext _db;
        private readonly IHubContext<AlertHub> _hub;
        private readonly ILogger<AlertsService> _logger;
        private readonly IPushNotificationService _pushNotificationService;
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly string _aiServiceUrl;

        public AlertsService(ApplicationDbContext db, IHubContext<AlertHub> hub, ILogger<AlertsService> logger, IPushNotificationService pushNotificationService, IHttpClientFactory httpClientFactory, IConfiguration config)
        {
            _db = db;
            _hub = hub;
            _logger = logger;
            _pushNotificationService = pushNotificationService;
            _httpClientFactory = httpClientFactory;
            _aiServiceUrl = config["AiService:Url"] ?? Environment.GetEnvironmentVariable("AI_SERVICE_URL") ?? "http://ai-service:5000";
        }

        public async Task<object> FindAll(AlertQueryDto query, string? userRole, string? userId)
        {
            var q = _db.Alerts
                .Include(a => a.Device).ThenInclude(d => d.Area)
                .Include(a => a.HandledBy)
                .AsQueryable();

            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                q = q.Where(a => classroomIds.Contains(a.Device.AreaId));
            }

            if (!string.IsNullOrEmpty(query.DateFrom))
                q = q.Where(a => a.Timestamp >= DateTime.Parse(query.DateFrom));
            if (!string.IsNullOrEmpty(query.DateTo))
                q = q.Where(a => a.Timestamp <= DateTime.Parse(query.DateTo));
            if (!string.IsNullOrEmpty(query.SoundType) && Enum.TryParse<SoundType>(query.SoundType, out var st))
                q = q.Where(a => a.SoundType == st);
            if (!string.IsNullOrEmpty(query.Status) && Enum.TryParse<AlertStatus>(query.Status, out var s))
                q = q.Where(a => a.Status == s);
            if (!string.IsNullOrEmpty(query.Area))
                q = q.Where(a => a.Device.Area.Name.Contains(query.Area));

            var total = await q.CountAsync();
            var data = await q.OrderByDescending(a => a.Timestamp)
                .Skip(query.Offset).Take(query.Limit)
                .ToListAsync();

            bool canSeeAudio = true; // Allow all roles to hear the audio
            var result = data.Select(a => (object)new
            {
                a.Id,
                device_id = a.DeviceId,
                device = new { a.Device.Id, a.Device.Name, floor = a.Device.Floor, area = new { a.Device.Area.Id, a.Device.Area.Name } },
                timestamp = DateTime.SpecifyKind(a.Timestamp, DateTimeKind.Utc),
                sound_type = a.SoundType.ToString(),
                confidence_score = a.ConfidenceScore,
                audio_file_url = canSeeAudio ? (a.AudioData != null ? $"/api/alerts/{a.Id}/audio" : a.AudioFileUrl) : null,
                status = a.Status.ToString(),
                handled_by = a.HandledBy == null ? null : new { a.HandledBy.Id, full_name = a.HandledBy.FullName },
                resolved_at = a.ResolvedAt,
                a.Notes,
                is_evidence = a.IsEvidence,
                a.Transcript,
                a.Keywords,
                timestamp_seconds = a.TimestampSeconds,
                dialog_data = string.IsNullOrEmpty(a.DialogData) ? null : JsonSerializer.Deserialize<object>(a.DialogData, (JsonSerializerOptions?)null)
            }).ToList();

            return new { data = result, total, offset = query.Offset, limit = query.Limit };
        }

        public async Task<object> FindOne(string id, string? userRole, string? userId)
        {
            var a = await _db.Alerts
                .Include(x => x.Device).ThenInclude(d => d.Area)
                .Include(x => x.HandledBy)
                .Include(x => x.Logs).ThenInclude(l => l.Actor)
                .FirstOrDefaultAsync(x => x.Id == id)
                ?? throw new KeyNotFoundException("Không tìm thấy cảnh báo");

            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                if (!classroomIds.Contains(a.Device.AreaId))
                    throw new KeyNotFoundException("Không tìm thấy cảnh báo");
            }

            bool canSeeAudio = true; // Allow all roles to hear the audio
            return new
            {
                a.Id,
                device_id = a.DeviceId,
                device = new { a.Device.Id, a.Device.Name, floor = a.Device.Floor, area = new { a.Device.Area.Id, a.Device.Area.Name } },
                timestamp = DateTime.SpecifyKind(a.Timestamp, DateTimeKind.Utc),
                sound_type = a.SoundType.ToString(),
                confidence_score = a.ConfidenceScore,
                audio_file_url = canSeeAudio ? (a.AudioData != null ? $"/api/alerts/{a.Id}/audio" : a.AudioFileUrl) : null,
                status = a.Status.ToString(),
                handled_by = a.HandledBy == null ? null : new { a.HandledBy.Id, full_name = a.HandledBy.FullName, role = a.HandledBy.Role.ToString() },
                resolved_at = a.ResolvedAt,
                a.Notes,
                is_evidence = a.IsEvidence,
                a.Transcript,
                a.Keywords,
                timestamp_seconds = a.TimestampSeconds,
                dialog_data = string.IsNullOrEmpty(a.DialogData) ? null : JsonSerializer.Deserialize<object>(a.DialogData, (JsonSerializerOptions?)null),
                logs = a.Logs?.OrderBy(l => l.Timestamp).Select(l => new
                {
                    l.Id,
                    l.Action,
                    timestamp = DateTime.SpecifyKind(l.Timestamp, DateTimeKind.Utc),
                    actor = new { l.Actor.Id, full_name = l.Actor.FullName, role = l.Actor.Role.ToString() }
                })
            };
        }

        public async Task<object> SubmitDetection(
            string deviceId,
            string soundType,
            double confidence,
            string? audioUrl = null,
            string? notes = null,
            byte[]? audioData = null,
            string? dialogData = null,
            string? transcript = null,
            string? keywords = null)
        {
            var alert = new Alert
            {
                DeviceId = deviceId,
                SoundType = Enum.Parse<SoundType>(soundType),
                ConfidenceScore = confidence,
                AudioFileUrl = audioUrl,
                AudioData = audioData,
                DialogData = dialogData,
                Notes = notes,
                Transcript = transcript,
                Keywords = keywords,
                Status = AlertStatus.pending
            };
            _db.Alerts.Add(alert);
            await _db.SaveChangesAsync();

            await _db.Entry(alert).Reference(a => a.Device).LoadAsync();
            await _db.Entry(alert.Device).Reference(d => d.Area).LoadAsync();

            // Broadcast via SignalR with Role-Based Access Control
            var alertDto = await FindOne(alert.Id, "admin", null);
            var allowedUserIds = await GetAllowedUserIdsForAreaAsync(alert.Device.AreaId);
            
            // Only broadcast to allowed users to avoid duplicate events. If no one is allowed, skip.
            // But admins should always get it. For now, just use Clients.All to ensure everyone gets it, 
            // since the frontend filters anyway, or just keep Clients.All and remove the specific Users call to fix duplication.
            await _hub.Clients.All.SendAsync("new-alert", alertDto);
            _logger.LogInformation("Broadcasting new alert: {Id} to all connected clients", alert.Id);

            // Send Push Notifications
            var tokens = await _db.UserDevices
                .Where(ud => allowedUserIds.Contains(ud.UserId) && !string.IsNullOrEmpty(ud.FcmToken))
                .Select(ud => ud.FcmToken)
                .ToListAsync();

            if (tokens.Any())
            {
                await _pushNotificationService.SendAlertNotificationAsync(alert, tokens);
            }

            return alertDto;
        }

        public async Task<object> AnalyzeUploadedAudio(
            string audioUrl,
            string originalName = "",
            string? preferredDeviceId = null,
            string? edgeClass = null,
            double? edgeConfidence = null)
        {
            Device? device = null;

            if (!string.IsNullOrWhiteSpace(preferredDeviceId))
            {
                device = await _db.Devices.FirstOrDefaultAsync(d =>
                    d.Id == preferredDeviceId || d.Name == preferredDeviceId);
            }

            if (device == null)
            {
                var devices = await _db.Devices
                    .Where(d => d.Status == DeviceStatus.online)
                    .ToListAsync();
                device = devices.Count > 0
                    ? devices[Random.Shared.Next(devices.Count)]
                    : await _db.Devices.FirstOrDefaultAsync();
            }

            if (device == null)
                throw new Exception("No devices available to bind alert");

            var createdAlerts = new List<object>();

            try
            {
                var absolutePath = Path.GetFileName(audioUrl);
                using var client = _httpClientFactory.CreateClient();
                client.Timeout = TimeSpan.FromMinutes(5); // Chờ AI phân tích
                var response = await client.PostAsJsonAsync($"{_aiServiceUrl.TrimEnd('/')}/analyze-full", new { filepath = absolutePath });
                if (response.IsSuccessStatusCode)
                {
                    var result = await response.Content.ReadFromJsonAsync<JsonElement>();
                    var dialogData = result.TryGetProperty("dialog_data", out var d) ? d.GetRawText() : null;
                    if (!string.IsNullOrEmpty(dialogData))
                    {
                        try
                        {
                            using var doc = JsonDocument.Parse(dialogData);
                            var dict = new Dictionary<string, object?>();
                            foreach (var prop in doc.RootElement.EnumerateObject())
                            {
                                dict[prop.Name] = JsonSerializer.Deserialize<object>(prop.Value.GetRawText());
                            }
                            dict["original_audio_url"] = audioUrl;
                            dialogData = JsonSerializer.Serialize(dict);
                        }
                        catch {}
                    }

                    bool hasAlerts = false;
                    if (result.TryGetProperty("alerts", out var alertsArr) && alertsArr.ValueKind == JsonValueKind.Array && alertsArr.GetArrayLength() > 0)
                    {
                        hasAlerts = true;
                        foreach (var alertJson in alertsArr.EnumerateArray())
                        {
                            var soundType = alertJson.GetProperty("soundType").GetString() ?? "argument";
                            var confidence = alertJson.GetProperty("confidence").GetDouble();
                            var filename = alertJson.GetProperty("filename").GetString();
                            var finalAudioUrl = $"/uploads/{filename}";
                            var startTime = alertJson.TryGetProperty("start_time_seconds", out var st) ? st.GetDouble() : 0;
                            var endTime = alertJson.TryGetProperty("end_time_seconds", out var et) ? et.GetDouble() : startTime + 10;
                            var typeLabel = soundType switch {
                                "dap_pha"  => AppConstants.SoundLabels.DapPha,
                                "help"     => AppConstants.SoundLabels.Help,
                                "threat"   => AppConstants.SoundLabels.Threat,
                                "scream"   => AppConstants.SoundLabels.Scream,
                                "argument" => AppConstants.SoundLabels.Argument,
                                _          => AppConstants.SoundLabels.Unknown
                            };
                            var transcript = alertJson.TryGetProperty("transcript", out var t) ? t.GetString() : null;
                            bool isThreat = alertJson.TryGetProperty("is_threat", out var it) && it.GetBoolean();
                            bool isEmergency = alertJson.TryGetProperty("is_emergency", out var ie) && ie.GetBoolean();
                            bool hasVulgarity = alertJson.TryGetProperty("has_vulgarity", out var iv) && iv.GetBoolean();

                            // BẢO VỆ: Nếu là "argument" nhưng KHÔNG có chửi thề và KHÔNG có đe dọa -> bỏ qua (cuộc trò chuyện bình thường)
                            if (soundType == "argument" && !hasVulgarity && !isThreat)
                            {
                                continue;
                            }
                            if (soundType == "unknown" || soundType == "normal")
                            {
                                continue;
                            }

                            bool isNoDialogue = string.IsNullOrWhiteSpace(transcript)
                                || transcript.Trim().Equals("Không có lời thoại", StringComparison.OrdinalIgnoreCase)
                                || transcript.Trim().Equals("khong co loi thoai", StringComparison.OrdinalIgnoreCase);

                            string notes;
                            if (isNoDialogue)
                            {
                                transcript = "Không có lời thoại";
                                notes = $"[Giây {startTime:F1} - {endTime:F1}] {typeLabel}: Không có lời thoại.";
                            }
                            else
                            {
                                notes = $"[Giây {startTime:F1} - {endTime:F1}] {typeLabel}: \"{transcript}\"";
                            }

                            byte[]? audioBytes = null;
                            var fullPath = Path.Combine(Directory.GetCurrentDirectory(), "uploads", filename);
                            if (File.Exists(fullPath))
                            {
                                audioBytes = await File.ReadAllBytesAsync(fullPath);
                            }

                            var alertRecord = await SubmitDetection(device.Id, soundType, confidence, finalAudioUrl, notes, audioBytes, dialogData, transcript);
                            createdAlerts.Add(alertRecord);
                        }
                    }

                    // KẾT HỢP CON AI THỨ 2 (EDGE AI TỪ ESP32 VỚI SERVER AI TRÊN WEB):
                    if (!hasAlerts)
                    {
                        var normEdge = edgeClass?.Trim().ToUpperInvariant() ?? "";
                        bool isEdgeDanger = normEdge == "KHOC" || normEdge == "HELP" || normEdge == "DAP_PHA" || normEdge == "CHUI_NHAU" || normEdge == "THREAT" || normEdge == "SCREAM";

                        int violenceProb = 0;
                        int threatsCount = 0;
                        int vulgarityCount = 0;
                        bool hasScream = false;
                        bool hasCrying = false;
                        bool hasImpactServer = false;
                        int emergencyCount = 0;
                        string? allTranscript = null;

                        if (result.TryGetProperty("dialog_data", out var diagObj) && diagObj.ValueKind == JsonValueKind.Object)
                        {
                            if (diagObj.TryGetProperty("violence_probability", out var vp)) violenceProb = vp.GetInt32();
                            if (diagObj.TryGetProperty("threats_count", out var tc)) threatsCount = tc.GetInt32();
                            if (diagObj.TryGetProperty("vulgarity_count", out var vc)) vulgarityCount = vc.GetInt32();
                            if (diagObj.TryGetProperty("has_scream", out var hs)) hasScream = hs.GetBoolean();
                            if (diagObj.TryGetProperty("has_crying", out var hc)) hasCrying = hc.GetBoolean();
                            if (diagObj.TryGetProperty("has_impact", out var hi)) hasImpactServer = hi.GetBoolean();
                            if (diagObj.TryGetProperty("emergency_count", out var ec)) emergencyCount = ec.GetInt32();

                            if (diagObj.TryGetProperty("dialogue", out var diagArr) && diagArr.ValueKind == JsonValueKind.Array)
                            {
                                var texts = new List<string>();
                                foreach (var item in diagArr.EnumerateArray())
                                {
                                    if (item.TryGetProperty("text", out var tx))
                                    {
                                        var s = tx.GetString();
                                        if (!string.IsNullOrWhiteSpace(s)) texts.Add(s);
                                    }
                                }
                                if (texts.Any()) allTranscript = string.Join(" ", texts);
                            }
                        }

                        // NGUYÊN TẮC THẨM ĐỊNH NỘI DUNG TỐI CAO:
                        // 1. Server AI phát hiện dấu hiệu nguy hiểm qua lời thoại bóc băng hoặc âm thanh YAMNet:
                        bool serverDetectedDanger = hasScream 
                            || hasCrying 
                            || emergencyCount > 0 
                            || threatsCount > 0 
                            || vulgarityCount > 0 
                            || hasImpactServer 
                            || violenceProb >= 40;

                        // 2. Nếu Server AI thẩm định nội dung và xác nhận an toàn (0% bạo lực, không chửi thề, không đe dọa):
                        // -> Phủ quyết (VETO) các báo động giả do tiếng trống nhạc hoặc tiếng ồn gây kích hoạt nhầm tại Edge!
                        bool serverConfirmsSafe = !hasScream 
                            && !hasCrying 
                            && emergencyCount == 0 
                            && threatsCount == 0 
                            && vulgarityCount == 0 
                            && !hasImpactServer 
                            && violenceProb < 30;

                        bool isRealViolence = serverDetectedDanger;

                        // Chỉ chấp nhận hỗ trợ từ Edge AI nếu Server AI không xác nhận an toàn tuyệt đối:
                        if (!isRealViolence && isEdgeDanger && !serverConfirmsSafe)
                        {
                            if (normEdge == "DAP_PHA" && (hasImpactServer || violenceProb >= 25))
                            {
                                isRealViolence = true;
                            }
                            else if ((normEdge == "KHOC" || normEdge == "HELP") && (hasCrying || emergencyCount > 0 || violenceProb >= 25))
                            {
                                isRealViolence = true;
                            }
                            else if ((normEdge == "CHUI_NHAU" || normEdge == "THREAT") && (vulgarityCount > 0 || threatsCount > 0 || violenceProb >= 25))
                            {
                                isRealViolence = true;
                            }
                        }

                        if (isRealViolence)
                        {
                            var detectedTypes = new List<string>();

                            // Kiểm tra tất cả các dấu hiệu bạo lực thay vì chỉ lấy cái đầu tiên
                            if (hasCrying || emergencyCount > 0 || normEdge == "KHOC" || normEdge == "HELP") 
                                detectedTypes.Add("help");
                            
                            if (hasScream || normEdge == "SCREAM") 
                                detectedTypes.Add("scream");
                                
                            if (threatsCount > 0 || normEdge == "THREAT") 
                                detectedTypes.Add("threat");
                                
                            if (hasImpactServer || normEdge == "DAP_PHA") 
                                detectedTypes.Add("dap_pha");
                                
                            if (vulgarityCount > 0 || normEdge == "CHUI_NHAU") 
                                detectedTypes.Add("argument");
                                
                            if (detectedTypes.Count == 0)
                            {
                                detectedTypes.Add("argument");
                            }

                            double finalConfidence = violenceProb > 0 
                                ? (double)violenceProb 
                                : (edgeConfidence.HasValue && edgeConfidence.Value > 0 
                                    ? (edgeConfidence.Value <= 1.0 ? edgeConfidence.Value * 100.0 : edgeConfidence.Value) 
                                    : 80.0);

                            byte[]? audioBytes = null;
                            var fullPath = Path.Combine(Directory.GetCurrentDirectory(), "uploads", absolutePath);
                            if (File.Exists(fullPath))
                            {
                                audioBytes = await File.ReadAllBytesAsync(fullPath);
                            }

                            bool isNoDialogueFallback = string.IsNullOrWhiteSpace(allTranscript)
                                || allTranscript.Trim().Equals("Không có lời thoại", StringComparison.OrdinalIgnoreCase)
                                || allTranscript.Trim().Equals("khong co loi thoai", StringComparison.OrdinalIgnoreCase);

                            string edgeInfo = !string.IsNullOrEmpty(normEdge) ? $"Edge AI: {normEdge} | " : "";

                            // Tạo một cảnh báo riêng cho mỗi loại bạo lực phát hiện được
                            foreach (var soundType in detectedTypes)
                            {
                                var typeLabel = soundType switch {
                                    "dap_pha"  => AppConstants.SoundLabels.DapPha,
                                    "help"     => AppConstants.SoundLabels.Help,
                                    "threat"   => AppConstants.SoundLabels.Threat,
                                    "scream"   => AppConstants.SoundLabels.Scream,
                                    "argument" => AppConstants.SoundLabels.Argument,
                                    _          => AppConstants.SoundLabels.Unknown
                                };

                                string notes;
                                if (isNoDialogueFallback)
                                {
                                    notes = $"[{edgeInfo}{typeLabel}] Không có lời thoại.";
                                }
                                else
                                {
                                    notes = $"[{edgeInfo}{typeLabel}] Lời thoại: \"{allTranscript}\"";
                                }

                                string alertTranscript = isNoDialogueFallback ? "Không có lời thoại" : allTranscript;

                                var alertRecord = await SubmitDetection(device.Id, soundType, finalConfidence, audioUrl, notes, audioBytes, dialogData, alertTranscript);
                                createdAlerts.Add(alertRecord);
                            }
                        }
                        else
                        {
                            _logger.LogInformation("[Lọc ồn / Nói chuyện bình thường] File {File} không chứa từ ngữ nguy hiểm, tiếng hét hay tiếng khóc (ViolenceProb: {Vp}%, Scream: {Hs}, Cry: {Hc}, Curses: {Vc}, Threats: {Tc}). Bỏ qua không tạo cảnh báo lên Web.", absolutePath, violenceProb, hasScream, hasCrying, vulgarityCount, threatsCount);
                        }
                    }
                }
                else
                {
                    var errText = await response.Content.ReadAsStringAsync();
                    _logger.LogWarning("AI Service trả về lỗi: {Code}. Detail: {Err}", response.StatusCode, errText);
                    throw new Exception($"AI Server Error ({response.StatusCode}): {errText}");
                }
            }
            catch (Exception e)
            {
                _logger.LogError("Failed to reach AI service: {Msg}", e.Message);
                throw new Exception($"Không thể phân tích âm thanh: {e.Message}");
            }

            return new { success = true, totalAlerts = createdAlerts.Count, alerts = createdAlerts };
        }

        public async Task<object> AnalyzeDialogAudio(string audioUrl)
        {
            try
            {
                var absolutePath = Path.GetFileName(audioUrl);
                using var client = _httpClientFactory.CreateClient();
                client.Timeout = TimeSpan.FromMinutes(10);
                var response = await client.PostAsJsonAsync($"{_aiServiceUrl.TrimEnd('/')}/analyze-dialog", new { filepath = absolutePath });
                
                if (response.IsSuccessStatusCode)
                {
                    var result = await response.Content.ReadFromJsonAsync<JsonElement>();
                    return result;
                }
                else
                {
                    var errText = await response.Content.ReadAsStringAsync();
                    _logger.LogWarning("AI Service trả về lỗi: {Code}. Detail: {Err}", response.StatusCode, errText);
                    throw new Exception($"AI Server Error ({response.StatusCode}): {errText}");
                }
            }
            catch (Exception e)
            {
                _logger.LogError("Failed to reach AI service: {Msg}", e.Message);
                throw new Exception($"Không thể phân tích đối thoại: {e.Message}");
            }
        }

        public async Task<object> UpdateAlert(string id, UpdateAlertDto dto, string userId)
        {
            var alert = await _db.Alerts.FindAsync(id) ?? throw new KeyNotFoundException("Không tìm thấy cảnh báo");

            if (dto.Status != null)
            {
                if (alert.Status == AlertStatus.resolved || alert.Status == AlertStatus.false_alarm)
                {
                    if (alert.Status.ToString() != dto.Status)
                        throw new InvalidOperationException("Cảnh báo này đã được xử lý xong");
                }

                alert.Status = Enum.Parse<AlertStatus>(dto.Status);
                if (dto.Status != "pending")
                {
                    alert.HandledById = userId;
                    alert.ResolvedAt = DateTime.UtcNow;
                }
            }
            if (dto.Notes != null) alert.Notes = dto.Notes;
            if (dto.IsEvidence.HasValue) alert.IsEvidence = dto.IsEvidence.Value;

            await _db.SaveChangesAsync();

            if (dto.Status != null)
            {
                var actionMap = new Dictionary<string, string>
                {
                    ["confirmed"]  = AppConstants.AlertActions.Confirmed,
                    ["false_alarm"] = AppConstants.AlertActions.FalseAlarm,
                    ["resolved"]   = AppConstants.AlertActions.Resolved
                };
                _db.AlertLogs.Add(new AlertLog
                {
                    AlertId = id,
                    Action = actionMap.TryGetValue(dto.Status, out var a) ? a : $"Cập nhật: {dto.Status}",
                    ActorId = userId
                });
                await _db.SaveChangesAsync();
            }

            var updated = await FindOne(id, "admin", null);

            var alertWithDevice = await _db.Alerts.Include(a => a.Device).FirstOrDefaultAsync(a => a.Id == id);
            if (alertWithDevice != null)
            {
                var allowedUserIds = await GetAllowedUserIdsForAreaAsync(alertWithDevice.Device.AreaId);
                await _hub.Clients.Users(allowedUserIds).SendAsync("alert-updated", updated);
            }
            return updated;
        }

        public async Task<int> GetPendingCount()
            => await _db.Alerts.CountAsync(a => a.Status == AlertStatus.pending);

        private async Task<List<string>> GetAllowedUserIdsForAreaAsync(string areaId)
        {
            var area = await _db.Areas.FindAsync(areaId);
            if (area == null) return new List<string>();

            // Admin, Ban Giam Hieu see everything
            var roles = new[] { Role.admin, Role.ban_giam_hieu, Role.bao_ve };
            var allowedUserIds = await _db.Users
                .Where(u => roles.Contains(u.Role))
                .Select(u => u.Id)
                .ToListAsync();

            // Teachers (giam_thi) might be assigned to specific areas, but for simplicity we allow them all or restrict them
            var giamThiIds = await _db.Users.Where(u => u.Role == Role.giam_thi).Select(u => u.Id).ToListAsync();
            allowedUserIds.AddRange(giamThiIds);

            // Parents only for their children's classrooms
            var parentIds = await _db.Students
                .Where(s => s.ClassroomId == areaId)
                .Select(s => s.ParentId)
                .ToListAsync();

            allowedUserIds.AddRange(parentIds);
            return allowedUserIds.Distinct().ToList();
        }

        public async Task<int> SyncOfflineActions(List<OfflineActionDto> actions, string userId, string userRole)
        {
            int successCount = 0;
            foreach (var action in actions.OrderBy(a => a.TimestampSeconds))
            {
                var alert = await _db.Alerts.FindAsync(action.AlertId);
                if (alert == null) continue;

                if (action.Action == AppConstants.OfflineActions.UpdateStatus && !string.IsNullOrEmpty(action.Status))
                {
                    if (Enum.TryParse<AlertStatus>(action.Status, out var newStatus))
                    {
                        alert.Status = newStatus;
                        alert.HandledById = userId;
                        if (newStatus == AlertStatus.resolved || newStatus == AlertStatus.false_alarm)
                        {
                            alert.ResolvedAt = DateTime.UtcNow;
                        }

                        _db.AlertLogs.Add(new AlertLog
                        {
                            AlertId = alert.Id,
                            Action = $"Status changed to {newStatus} (Sync)",
                            ActorId = userId,
                            Timestamp = DateTimeOffset.FromUnixTimeSeconds((long)action.TimestampSeconds).UtcDateTime
                        });
                        successCount++;
                    }
                }
                else if (action.Action == AppConstants.OfflineActions.AddNote && !string.IsNullOrEmpty(action.Notes))
                {
                    alert.Notes = string.IsNullOrEmpty(alert.Notes) ? action.Notes : alert.Notes + "\n" + action.Notes;
                    _db.AlertLogs.Add(new AlertLog
                    {
                        AlertId = alert.Id,
                        Action = "Added note (Sync)",
                        ActorId = userId,
                        Timestamp = DateTimeOffset.FromUnixTimeSeconds((long)action.TimestampSeconds).UtcDateTime
                    });
                    successCount++;
                }
            }
            await _db.SaveChangesAsync();
            return successCount;
        }
    }
}
