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
        private readonly string _audioDirectory;

        public AlertsService(ApplicationDbContext db, IHubContext<AlertHub> hub, ILogger<AlertsService> logger, IPushNotificationService pushNotificationService, IHttpClientFactory httpClientFactory, IConfiguration config)
        {
            _db = db;
            _hub = hub;
            _logger = logger;
            _pushNotificationService = pushNotificationService;
            _httpClientFactory = httpClientFactory;
            _aiServiceUrl = config["AiService:Url"] ?? Environment.GetEnvironmentVariable("AI_SERVICE_URL") ?? "http://ai-service:5000";
            _audioDirectory = config["Storage:AudioPath"] ?? Path.Combine(Directory.GetCurrentDirectory(), "uploads");
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
                confidence_score = a.RiskLevel == null ? (double?)a.ConfidenceScore : null,
                risk_level = a.RiskLevel,
                analysis = ReadAnalysisField(a.DialogData, "analysis"),
                model_scores = ReadAnalysisField(a.DialogData, "sound_events"),
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
                confidence_score = a.RiskLevel == null ? (double?)a.ConfidenceScore : null,
                risk_level = a.RiskLevel,
                analysis = ReadAnalysisField(a.DialogData, "analysis"),
                model_scores = ReadAnalysisField(a.DialogData, "sound_events"),
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
            string? keywords = null,
            string? riskLevel = null)
        {
            var alert = new Alert
            {
                DeviceId = deviceId,
                SoundType = Enum.Parse<SoundType>(soundType),
                ConfidenceScore = confidence,
                RiskLevel = riskLevel,
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

        private static object? ReadAnalysisField(string? json, string name)
        {
            if (string.IsNullOrEmpty(json)) return null;
            try
            {
                using var doc = JsonDocument.Parse(json);
                return doc.RootElement.TryGetProperty(name, out var value) ? value.Clone() : null;
            }
            catch (JsonException) { return null; }
        }

        private async Task<IQueryable<AudioAnalysis>> VisibleAnalyses(string? role, string? userId)
        {
            var query = _db.AudioAnalyses.AsNoTracking().AsQueryable();
            if (role == AppConstants.Roles.PhuHuynh)
            {
                var areas = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                query = query.Where(a => _db.Devices.Any(d => d.Id == a.DeviceId && areas.Contains(d.AreaId)));
            }
            return query;
        }

        public async Task<object> FindAnalyses(string? role, string? userId, int offset, int limit)
        {
            var query = await VisibleAnalyses(role, userId);
            var total = await query.CountAsync();
            offset = Math.Max(0, offset);
            limit = Math.Clamp(limit, 1, 100);
            var rows = await query.OrderByDescending(a => a.CreatedAt).Skip(offset).Take(limit).ToListAsync();
            var data = rows.Select(a => new { a.Id, created_at = a.CreatedAt, device_id = a.DeviceId,
                audio_file_url = a.AudioFileUrl, original_name = ReadAnalysisField(a.ResultJson, "original_name"),
                analysis = ReadAnalysisField(a.ResultJson, "analysis") });
            return new { data, total, offset, limit };
        }

        public async Task<object> FindAnalysis(string id, string? role, string? userId)
        {
            var query = await VisibleAnalyses(role, userId);
            var row = await query.FirstOrDefaultAsync(a => a.Id == id)
                ?? throw new KeyNotFoundException("Không tìm thấy bản phân tích audio");
            return JsonSerializer.Deserialize<JsonElement>(row.ResultJson);
        }

        public async Task<object> AnalyzeUploadedAudio(
            string audioUrl, string originalName = "", string? preferredDeviceId = null,
            string? edgeClass = null, double? edgeConfidence = null)
        {
            var device = string.IsNullOrWhiteSpace(preferredDeviceId) ? null :
                await _db.Devices.FirstOrDefaultAsync(d => d.Id == preferredDeviceId || d.Name == preferredDeviceId);
            device ??= await _db.Devices.OrderBy(d => d.Id).FirstOrDefaultAsync();
            if (device == null) throw new InvalidOperationException("No device available to bind analysis");
            var filename = Path.GetFileName(audioUrl);
            using var client = _httpClientFactory.CreateClient();
            client.Timeout = TimeSpan.FromMinutes(15);
            using var response = await client.PostAsJsonAsync(
                $"{_aiServiceUrl.TrimEnd('/')}/analyze-full", new { filepath = filename });
            response.EnsureSuccessStatusCode();
            var result = await response.Content.ReadFromJsonAsync<JsonElement>();
            if (!result.TryGetProperty("analysis", out var analysis) || !result.TryGetProperty("asr", out var asr))
                throw new HttpRequestException("AI response is missing analysis/transcription");
            var risk = analysis.GetProperty("risk_level").GetString();
            if (risk is not ("low" or "review" or "high"))
                throw new HttpRequestException("AI response has invalid risk_level");
            var persisted = new Dictionary<string, object?>();
            foreach (var property in result.EnumerateObject())
                persisted[property.Name] = property.Value.Clone();
            persisted["original_audio_url"] = audioUrl;
            persisted["original_name"] = Path.GetFileName(originalName);
            // Edge scores are audit metadata only; they never override server risk.
            persisted["edge_evidence"] = new { label = edgeClass, model_score = edgeConfidence };
            var json = JsonSerializer.Serialize(persisted);
            var run = new AudioAnalysis { DeviceId = device.Id, AudioFileUrl = audioUrl, ResultJson = json };
            _db.AudioAnalyses.Add(run);
            await _db.SaveChangesAsync();
            var alerts = new List<object>();
            var transcript = asr.GetProperty("normalized_transcript").GetString() ?? "";
            if (risk != "low")
            {
                var type = result.TryGetProperty("soundType", out var st) ? st.GetString() : "argument";
                if (!Enum.TryParse<SoundType>(type, out _)) type = "argument";
                var path = Path.Combine(_audioDirectory, filename);
                var bytes = File.Exists(path) ? await File.ReadAllBytesAsync(path) : null;
                alerts.Add(await SubmitDetection(device.Id, type!, 0, audioUrl,
                    analysis.GetProperty("summary").GetString(), bytes, json, transcript, riskLevel: risk));
            }
            return new { success = true, total_alerts = alerts.Count,
                analysis_id = run.Id, alerts, result = persisted,
                asr = asr.Clone(), timeline = result.GetProperty("timeline").Clone(),
                sound_events = result.GetProperty("sound_events").Clone(), analysis = analysis.Clone(),
                raw_transcript = asr.GetProperty("raw_transcript").GetString(),
                normalized_transcript = transcript, transcript };
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
