using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using SchoolGuardian.Api.Extensions;
using SchoolGuardian.Api.DTOs;
using SchoolGuardian.Api.Services;
using SchoolGuardian.Api.Data;

namespace SchoolGuardian.Api.Controllers
{
    [ApiController]
    [Route("api/alerts")]
    [Authorize]
    public class AlertsController : ControllerBase
    {
        private readonly AlertsService _svc;
        public AlertsController(AlertsService svc) => _svc = svc;

        [HttpGet]
        public async Task<IActionResult> FindAll([FromQuery] AlertQueryDto query)
        {
            var role = User.GetUserRole();
            var userId = User.GetUserId();
            return Ok(await _svc.FindAll(query, role, userId));
        }

        [AllowAnonymous]
        [HttpGet("test")]
        public async Task<IActionResult> FindAllTest([FromQuery] AlertQueryDto query)
        {
            return Ok(await _svc.FindAll(query, "admin", null));
        }

        [HttpGet("{id}")]
        public async Task<IActionResult> FindOne(string id)
        {
            var role = User.GetUserRole();
            var userId = User.GetUserId();
            try { return Ok(await _svc.FindOne(id, role, userId)); }
            catch (KeyNotFoundException ex) { return NotFound(new { message = ex.Message }); }
        }

        [HttpPost]
        [AllowAnonymous]
        public async Task<IActionResult> Create([FromBody] CreateAlertDto dto, [FromServices] IConfiguration config)
        {
            var token = Request.Headers["X-Device-Token"].FirstOrDefault();
            if (string.IsNullOrEmpty(token) || token != config["DeviceToken"])
                return Unauthorized(new { message = "Invalid Device Token" });
            return Ok(await _svc.SubmitDetection(dto.DeviceId, dto.SoundType, dto.ConfidenceScore, dto.AudioFileUrl));
        }

        [AllowAnonymous]
        [HttpPost("device-recording")]
        [RequestSizeLimit(2 * 1024 * 1024)]
        public async Task<IActionResult> UploadDeviceRecording(
            [FromQuery(Name = "device_id")] string deviceId,
            [FromQuery(Name = "type")] string eventType,
            [FromQuery] double confidence,
            [FromQuery(Name = "event_id")] string? eventId,
            [FromQuery(Name = "edge_class")] string? edgeClass,
            [FromServices] IConfiguration config,
            [FromServices] ApplicationDbContext db,
            [FromServices] IServiceScopeFactory scopeFactory)
        {
            var token = Request.Headers["X-Device-Token"].FirstOrDefault();
            if (string.IsNullOrEmpty(token) || token != config["DeviceToken"])
                return Unauthorized(new { message = "Invalid Device Token" });

            var normalizedEventType = eventType.Trim().ToLowerInvariant();
            var soundType = normalizedEventType switch
            {
                "analyze" => "analyze",
                "khoc" => "help",
                "dap_pha" => "dap_pha",
                "scream" => "scream",
                "help" => "help",
                "threat" => "threat",
                "argument" => "argument",
                _ => null
            };

            if (soundType == null)
                return BadRequest(new { message = "Unsupported event type" });

            var device = await db.Devices.FirstOrDefaultAsync(d =>
                d.Id == deviceId || d.Name == deviceId);
            device ??= await db.Devices.FirstOrDefaultAsync();

            if (device == null)
                return BadRequest(new { message = "No device exists on the website" });

            var safeEventId = string.IsNullOrWhiteSpace(eventId)
                ? Guid.NewGuid().ToString("N")
                : new string(eventId
                    .Where(c => char.IsLetterOrDigit(c) || c is '-' or '_')
                    .Take(96)
                    .ToArray());

            if (string.IsNullOrEmpty(safeEventId))
                safeEventId = Guid.NewGuid().ToString("N");

            var fileName = $"{safeEventId}_{normalizedEventType}.wav";
            var audioUrl = $"/uploads/{fileName}";
            var uploadsDir = Path.Combine(Directory.GetCurrentDirectory(), "uploads");
            Directory.CreateDirectory(uploadsDir);
            var analysisMarker = Path.Combine(uploadsDir, $"{safeEventId}.analyzed");

            if (normalizedEventType == "analyze" && System.IO.File.Exists(analysisMarker))
            {
                return Ok(new
                {
                    success = true,
                    duplicate = true,
                    analyzed = true,
                    file = fileName
                });
            }

            var existing = normalizedEventType == "analyze"
                ? null
                : await db.Alerts.FirstOrDefaultAsync(a => a.AudioFileUrl == audioUrl);
            if (existing != null)
            {
                return Ok(new
                {
                    success = true,
                    duplicate = true,
                    alert_id = existing.Id,
                    file = fileName
                });
            }

            using var buffer = new MemoryStream();
            await Request.Body.CopyToAsync(buffer, HttpContext.RequestAborted);
            var audioBytes = buffer.ToArray();

            if (audioBytes.Length < 44 || audioBytes.Length > 2 * 1024 * 1024)
                return BadRequest(new { message = "Invalid WAV size" });

            if (System.Text.Encoding.ASCII.GetString(audioBytes, 0, 4) != "RIFF" ||
                System.Text.Encoding.ASCII.GetString(audioBytes, 8, 4) != "WAVE")
                return BadRequest(new { message = "Body must be a WAV file" });

            await System.IO.File.WriteAllBytesAsync(
                Path.Combine(uploadsDir, fileName),
                audioBytes,
                HttpContext.RequestAborted);

            if (normalizedEventType == "analyze")
            {
                var targetDeviceId = device.Id;
                _ = Task.Run(async () =>
                {
                    try
                    {
                        using var scope = scopeFactory.CreateScope();
                        var scopedSvc = scope.ServiceProvider.GetRequiredService<AlertsService>();
                        await scopedSvc.AnalyzeUploadedAudio(
                            audioUrl,
                            fileName,
                            targetDeviceId,
                            edgeClass,
                            confidence);

                        await System.IO.File.WriteAllTextAsync(
                            analysisMarker,
                            DateTime.UtcNow.ToString("O"),
                            CancellationToken.None);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"[Background AI Analyze Error]: {ex.Message}");
                    }
                });

                return Ok(new
                {
                    success = true,
                    local_saved = true,
                    queued = true,
                    file = fileName
                });
            }


            var confidencePercent = Math.Clamp(
                confidence <= 1.0 ? confidence * 100.0 : confidence,
                0.0,
                100.0);

            string espNote = eventType.ToLowerInvariant() switch
            {
                "dap_pha" => "ESP32 nhận diện: Đập phá (Không có lời thoại)",
                "khoc" => "ESP32 nhận diện: Tiếng khóc (Không có lời thoại)",
                _ => $"ESP32 nhận diện: {eventType}"
            };

            var alert = await _svc.SubmitDetection(
                device.Id,
                soundType,
                confidencePercent,
                audioUrl,
                espNote,
                audioBytes,
                null,
                (soundType == "dap_pha" || soundType == "help") ? "Không có lời thoại" : null);

            return Ok(new
            {
                success = true,
                local_saved = true,
                event_type = eventType,
                website_sound_type = soundType,
                file = fileName,
                alert
            });
        }

        [HttpPost("upload")]
        [AllowAnonymous]
        public async Task<IActionResult> UploadAudio(IFormFile? audio, [FromServices] IConfiguration config)
        {
            // Cho phép ESP32/thiết bị phần cứng dùng X-Device-Token thay cho JWT
            var deviceToken = Request.Headers["X-Device-Token"].FirstOrDefault();
            bool isAuthenticated = User.Identity?.IsAuthenticated == true;
            bool hasValidDeviceToken = !string.IsNullOrEmpty(deviceToken) && deviceToken == config["DeviceToken"];

            if (!isAuthenticated && !hasValidDeviceToken)
                return Unauthorized(new { message = "Vui lòng đăng nhập hoặc cung cấp Device Token hợp lệ" });

            if (audio == null || audio.Length == 0)
                return BadRequest(new { error = "No file uploaded" });

            if (audio.Length > 50 * 1024 * 1024)
                return BadRequest(new { error = "File size exceeds 50MB limit" });

            var ext = Path.GetExtension(audio.FileName).ToLower();
            var allowedExts = new[] { ".wav", ".mp3", ".m4a", ".mp4", ".webm", ".mkv", ".mov", ".avi", ".aac", ".ogg" };
            if (!allowedExts.Contains(ext))
                return BadRequest(new { error = "Invalid file type. Allowed audio & video: .wav, .mp3, .m4a, .mp4, .webm, .mkv, .mov" });

            var uploadsDir = Path.Combine(Directory.GetCurrentDirectory(), "uploads");
            Directory.CreateDirectory(uploadsDir);
            var fileName = $"{Guid.NewGuid():N}{Path.GetExtension(audio.FileName)}";
            var filePath = Path.Combine(uploadsDir, fileName);

            using (var stream = System.IO.File.Create(filePath))
                await audio.CopyToAsync(stream);

            return Ok(await _svc.AnalyzeUploadedAudio($"/uploads/{fileName}", audio.FileName));
        }

        public class AnalyzeExistingDto
        {
            public string FileName { get; set; } = string.Empty;
        }

        [HttpPost("analyze-existing")]
        [AllowAnonymous]
        public async Task<IActionResult> AnalyzeExisting([FromBody] AnalyzeExistingDto dto, [FromServices] IConfiguration config)
        {
            var deviceToken = Request.Headers["X-Device-Token"].FirstOrDefault();
            bool isAuthenticated = User.Identity?.IsAuthenticated == true;
            bool hasValidDeviceToken = !string.IsNullOrEmpty(deviceToken) && deviceToken == config["DeviceToken"];

            if (!isAuthenticated && !hasValidDeviceToken)
                return Unauthorized(new { message = "Vui lòng đăng nhập hoặc cung cấp Device Token hợp lệ" });

            if (string.IsNullOrEmpty(dto.FileName))
                return BadRequest(new { error = "FileName is required" });

            // File đã nằm trong thư mục uploads/ (hoặc tai-lieu) nhờ websocket_receiver
            return Ok(await _svc.AnalyzeUploadedAudio($"/uploads/{dto.FileName}", dto.FileName));
        }

        [HttpPost("upload-dialog")]
        public async Task<IActionResult> UploadDialogAudio(IFormFile audio)
        {
            if (audio == null || audio.Length == 0)
                return BadRequest(new { error = "No file uploaded" });

            if (audio.Length > 50 * 1024 * 1024)
                return BadRequest(new { error = "File size exceeds 50MB limit" });

            var ext = Path.GetExtension(audio.FileName).ToLower();
            var allowedExts = new[] { ".wav", ".mp3", ".m4a" };
            if (!allowedExts.Contains(ext))
                return BadRequest(new { error = "Invalid file type. Allowed: .wav, .mp3, .m4a" });

            var uploadsDir = Path.Combine(Directory.GetCurrentDirectory(), "uploads");
            Directory.CreateDirectory(uploadsDir);
            var fileName = $"{Guid.NewGuid():N}{Path.GetExtension(audio.FileName)}";
            var filePath = Path.Combine(uploadsDir, fileName);

            using (var stream = System.IO.File.Create(filePath))
                await audio.CopyToAsync(stream);

            return Ok(await _svc.AnalyzeDialogAudio($"/uploads/{fileName}"));
        }

        [HttpPatch("{id}")]
        public async Task<IActionResult> Update(string id, [FromBody] UpdateAlertDto dto)
        {
            var userId = User.GetUserId();

            if (string.IsNullOrEmpty(userId))
                return Unauthorized(new { message = "Invalid user token" });

            try { return Ok(await _svc.UpdateAlert(id, dto, userId)); }
            catch (KeyNotFoundException ex) { return NotFound(new { message = ex.Message }); }
            catch (InvalidOperationException ex) { return BadRequest(new { message = ex.Message }); }
        }

        [HttpPost("sync")]
        public async Task<IActionResult> Sync([FromBody] List<OfflineActionDto> actions)
        {
            var userId = User.GetUserId();
            var userRole = User.GetUserRole();

            if (string.IsNullOrEmpty(userId))
                return Unauthorized(new { message = "Invalid user token" });

            try
            {
                int syncedCount = await _svc.SyncOfflineActions(actions, userId, userRole);
                return Ok(new { message = $"Đã đồng bộ {syncedCount} thao tác ngoại tuyến thành công", syncedCount });
            }
            catch (Exception ex)
            {
                return BadRequest(new { message = ex.Message });
            }
        }

        [AllowAnonymous]
        [HttpGet("{id}/audio")]
        public async Task<IActionResult> GetAudio(string id, [FromServices] ApplicationDbContext db)
        {
            var alert = await db.Alerts.FindAsync(id);
            if (alert == null || alert.AudioData == null)
            {
                return NotFound();
            }

            var contentType = "audio/mpeg";
            if (!string.IsNullOrEmpty(alert.AudioFileUrl))
            {
                var ext = Path.GetExtension(alert.AudioFileUrl).ToLower();
                if (ext == ".wav") contentType = "audio/wav";
                else if (ext == ".m4a") contentType = "audio/mp4";
            }

            return File(alert.AudioData, contentType, enableRangeProcessing: true);
        }
    }
}
