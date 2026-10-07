using Microsoft.EntityFrameworkCore;
using SchoolGuardian.Api.Data;
using SchoolGuardian.Api.Models;

namespace SchoolGuardian.Api.Services
{
    public class StatisticsService
    {
        private readonly ApplicationDbContext _db;

        public StatisticsService(ApplicationDbContext db) => _db = db;

        public async Task<object> GetSummary(string? userRole, string? userId)
        {
            var q = _db.Alerts.AsQueryable();
            var d = _db.Devices.AsQueryable();

            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                q = q.Include(a => a.Device).Where(a => classroomIds.Contains(a.Device.AreaId));
                d = d.Where(x => classroomIds.Contains(x.AreaId));
            }

            var today = DateTime.UtcNow.Date;
            var devicesOnline = await d.CountAsync(x => x.Status == DeviceStatus.online);
            var totalDevices = await d.CountAsync();
            var alertsToday = await q.CountAsync(a => a.Timestamp >= today);
            var pendingUrgent = await q.CountAsync(a => a.Status == AlertStatus.pending &&
                (a.RiskLevel == "high" || (a.RiskLevel == null && a.ConfidenceScore >= 80)));
            var avgResponse = await GetAvgResponseTime(q);

            return new { devices_online = devicesOnline, total_devices = totalDevices, alerts_today = alertsToday, pending_urgent = pendingUrgent, avg_response_minutes = avgResponse };
        }

        private async Task<double> GetAvgResponseTime(IQueryable<Alert> q)
        {
            var since = DateTime.UtcNow.AddDays(-7);
            var handled = await q
                .Where(a => a.ResolvedAt != null && a.Timestamp >= since)
                .Select(a => new { a.Timestamp, a.ResolvedAt })
                .Take(100).ToListAsync();

            if (handled.Count == 0) return 0;
            return Math.Round(handled.Average(a => (a.ResolvedAt!.Value - a.Timestamp).TotalMinutes));
        }

        public async Task<List<object>> GetByType(string? userRole, string? userId)
        {
            var q = _db.Alerts.AsQueryable();
            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                q = q.Include(a => a.Device).Where(a => classroomIds.Contains(a.Device.AreaId));
            }

            return await q
                .GroupBy(a => a.SoundType)
                .Select(g => (object)new { sound_type = g.Key.ToString(), count = g.Count() })
                .ToListAsync();
        }

        public async Task<List<object>> GetByArea(string? userRole, string? userId)
        {
            var q = _db.Alerts.Include(a => a.Device).ThenInclude(d => d.Area).AsQueryable();
            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                q = q.Where(a => classroomIds.Contains(a.Device.AreaId));
            }

            var result = await q.GroupBy(a => a.Device.Area.Name)
                .Select(g => new { area = g.Key, count = g.Count() })
                .OrderByDescending(x => x.count)
                .ToListAsync();
            return result.Cast<object>().ToList();
        }

        public async Task<List<object>> GetTrend(string period, string? userRole, string? userId)
        {
            var q = _db.Alerts.AsQueryable();
            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                q = q.Include(a => a.Device).Where(a => classroomIds.Contains(a.Device.AreaId));
            }

            var daysBack = period switch { "week" => 28, "month" => 180, _ => 7 };
            var since = DateTime.UtcNow.AddDays(-daysBack);
            var alerts = await q.Where(a => a.Timestamp >= since).Select(a => a.Timestamp).ToListAsync();

            return alerts.GroupBy(ts => period switch
            {
                "month" => $"{ts.Year}-{ts.Month:D2}",
                "week" => ts.AddDays(-(int)ts.DayOfWeek).ToString("yyyy-MM-dd"),
                _ => ts.ToString("yyyy-MM-dd")
            })
            .Select(g => (object)new { date = g.Key, count = g.Count() })
            .ToList();
        }

        public async Task<List<object>> GetHeatmap(string? userRole, string? userId)
        {
            var q = _db.Alerts.Include(a => a.Device).ThenInclude(d => d.Area).AsQueryable();
            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                q = q.Where(a => classroomIds.Contains(a.Device.AreaId));
            }

            var since = DateTime.UtcNow.AddDays(-30);
            var alertsData = await q.Where(a => a.Timestamp >= since)
                .Select(a => new { AreaName = a.Device.Area.Name, Hour = a.Timestamp.Hour })
                .ToListAsync();

            return alertsData.GroupBy(a => a.AreaName)
                .Select(g => (object)new
                {
                    area = g.Key,
                    hours = Enumerable.Range(0, 24).Select(h => new { hour = h, count = g.Count(x => x.Hour == h) })
                }).ToList();
        }

        public async Task<object> GetAlertRatio(string? userRole, string? userId)
        {
            var q = _db.Alerts.AsQueryable();
            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                q = q.Include(a => a.Device).Where(a => classroomIds.Contains(a.Device.AreaId));
            }

            var confirmed = await q.CountAsync(a => a.Status == AlertStatus.confirmed);
            var falseAlarm = await q.CountAsync(a => a.Status == AlertStatus.false_alarm);
            var total = await q.CountAsync();
            return new { confirmed, false_alarm = falseAlarm, pending = total - confirmed - falseAlarm, total };
        }

        public async Task<List<object>> GetHourlyToday(string? userRole, string? userId)
        {
            var q = _db.Alerts.AsQueryable();
            if (userRole == AppConstants.Roles.PhuHuynh && !string.IsNullOrEmpty(userId))
            {
                var classroomIds = await _db.Students.Where(s => s.ParentId == userId).Select(s => s.ClassroomId).ToListAsync();
                q = q.Include(a => a.Device).Where(a => classroomIds.Contains(a.Device.AreaId));
            }

            var today = DateTime.UtcNow.Date;
            var hours = await q.Where(a => a.Timestamp >= today).Select(a => a.Timestamp.Hour).ToListAsync();
            return Enumerable.Range(0, 24)
                .Select(h => (object)new { hour = h, count = hours.Count(x => x == h) })
                .ToList();
        }
    }
}
