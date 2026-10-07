using Microsoft.EntityFrameworkCore;
using SchoolGuardian.Api.Data;
using SchoolGuardian.Api.Models;

namespace SchoolGuardian.Api.Services
{
    /// <summary>
    /// Tách business logic của phụ huynh ra khỏi controller.
    /// ParentController chỉ gọi vào đây, không truy cập DB trực tiếp.
    /// </summary>
    public class ParentService
    {
        private readonly ApplicationDbContext _db;

        public ParentService(ApplicationDbContext db) => _db = db;

        /// <summary>Lấy danh sách lớp học mà phụ huynh có con đang học.</summary>
        public async Task<List<string>> GetClassroomIdsAsync(string parentId)
            => await _db.Students
                .Where(s => s.ParentId == parentId)
                .Select(s => s.ClassroomId)
                .ToListAsync();

        /// <summary>Thống kê cảnh báo hôm nay theo lớp học của phụ huynh.</summary>
        public async Task<object> GetStatsAsync(string parentId)
        {
            var classroomIds = await GetClassroomIdsAsync(parentId);
            if (!classroomIds.Any())
                return new { alerts_today = 0, alerts_by_type = Array.Empty<object>(), hourly_trend = Array.Empty<object>() };

            var today = DateTime.UtcNow.Date;
            var alertsQuery = _db.Alerts
                .Include(a => a.Device)
                .Where(a => classroomIds.Contains(a.Device.AreaId) && a.Timestamp >= today);

            var totalAlerts = await alertsQuery.CountAsync();

            var alertsByType = await alertsQuery
                .GroupBy(a => a.SoundType)
                .Select(g => new { sound_type = g.Key.ToString(), count = g.Count() })
                .ToListAsync();

            var hourlyTrend = await alertsQuery
                .GroupBy(a => a.Timestamp.Hour)
                .Select(g => new { hour = g.Key, count = g.Count() })
                .ToListAsync();

            return new
            {
                alerts_today  = totalAlerts,
                alerts_by_type = alertsByType,
                hourly_trend  = hourlyTrend
            };
        }

        /// <summary>Lấy danh sách cảnh báo trong các lớp học của phụ huynh.</summary>
        public async Task<List<object>> GetAlertsAsync(string parentId, string? soundType = null)
        {
            var classroomIds = await GetClassroomIdsAsync(parentId);
            if (!classroomIds.Any())
                return new List<object>();

            var query = _db.Alerts
                .Include(a => a.Device).ThenInclude(d => d.Area)
                .Where(a => classroomIds.Contains(a.Device.AreaId));

            if (!string.IsNullOrEmpty(soundType) && Enum.TryParse<SoundType>(soundType, true, out var parsedType))
                query = query.Where(a => a.SoundType == parsedType);

            return await query
                .OrderByDescending(a => a.Timestamp)
                .Take(50)
                .Select(a => (object)new
                {
                    id               = a.Id,
                    timestamp        = a.Timestamp,
                    sound_type       = a.SoundType.ToString(),
                    confidence_score = a.RiskLevel == null ? (double?)a.ConfidenceScore : null,
                    risk_level       = a.RiskLevel,
                    status           = a.Status.ToString(),
                    audio_file_url   = a.AudioFileUrl,
                    device_name      = a.Device.Name,
                    area_name        = a.Device.Area.Name
                })
                .ToListAsync();
        }
    }
}
