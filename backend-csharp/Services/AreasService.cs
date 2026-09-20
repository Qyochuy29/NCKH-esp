using Microsoft.EntityFrameworkCore;
using SchoolGuardian.Api.Data;
using SchoolGuardian.Api.DTOs;
using SchoolGuardian.Api.Models;

namespace SchoolGuardian.Api.Services
{
    public class AreasService
    {
        private readonly ApplicationDbContext _db;

        public AreasService(ApplicationDbContext db) => _db = db;

        public async Task<List<object>> FindAll()
        {
            var areas = await _db.Areas
                .OrderBy(a => a.Name)
                .Include(a => a.Devices)
                .ToListAsync();

            return areas.Select(a => (object)new
            {
                a.Id,
                a.Name,
                a.Description,
                created_at = a.CreatedAt,
                device_count = a.Devices?.Count ?? 0
            }).ToList();
        }

        public async Task<object> FindOne(string id)
        {
            var area = await _db.Areas
                .Include(a => a.Devices.OrderBy(d => d.Floor))
                .FirstOrDefaultAsync(a => a.Id == id)
                ?? throw new KeyNotFoundException("Không tìm thấy khu vực");

            return new
            {
                area.Id,
                area.Name,
                area.Description,
                created_at = area.CreatedAt,
                device_count = area.Devices?.Count ?? 0,
                devices = area.Devices?.Select(d => new { d.Id, d.Name, status = d.Status.ToString(), d.Floor })
            };
        }

        public async Task<Area> Create(CreateAreaDto dto)
        {
            if (await _db.Areas.AnyAsync(a => a.Name == dto.Name))
                throw new InvalidOperationException("Tên khu vực đã tồn tại");

            var area = new Area { Name = dto.Name, Description = dto.Description };
            _db.Areas.Add(area);
            await _db.SaveChangesAsync();
            return area;
        }

        public async Task<Area> Update(string id, UpdateAreaDto dto)
        {
            var area = await _db.Areas.FindAsync(id) ?? throw new KeyNotFoundException("Không tìm thấy khu vực");
            if (dto.Name != null)
            {
                if (await _db.Areas.AnyAsync(a => a.Name == dto.Name && a.Id != id))
                    throw new InvalidOperationException("Tên khu vực đã tồn tại");
                area.Name = dto.Name;
            }
            if (dto.Description != null) area.Description = dto.Description;
            await _db.SaveChangesAsync();
            return area;
        }

        public async Task Remove(string id)
        {
            var area = await _db.Areas.FindAsync(id) ?? throw new KeyNotFoundException("Không tìm thấy khu vực");
            
            // Xóa tất cả các thiết bị thuộc khu vực này (việc xóa thiết bị sẽ kích hoạt xóa alerts nếu ta xử lý thủ công)
            var devices = await _db.Devices.Where(d => d.AreaId == id).ToListAsync();
            foreach (var d in devices)
            {
                var alerts = await _db.Alerts.Where(a => a.DeviceId == d.Id).ToListAsync();
                _db.Alerts.RemoveRange(alerts);
            }
            _db.Devices.RemoveRange(devices);

            _db.Areas.Remove(area);
            await _db.SaveChangesAsync();
        }
    }
}
