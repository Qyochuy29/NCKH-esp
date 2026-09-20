using System.ComponentModel.DataAnnotations;

namespace SchoolGuardian.Api.DTOs
{
    // ============================================================
    // Auth DTOs
    // ============================================================
    public class LoginDto
    {
        [Required(ErrorMessage = "Email không được để trống")]
        [EmailAddress(ErrorMessage = "Email không đúng định dạng")]
        public string Email { get; set; } = string.Empty;

        [Required(ErrorMessage = "Mật khẩu không được để trống")]
        [MinLength(6, ErrorMessage = "Mật khẩu phải có ít nhất 6 ký tự")]
        public string Password { get; set; } = string.Empty;
    }

    public class SocialLoginDto
    {
        [Required] public string Provider      { get; set; } = string.Empty;
        [Required] public string ProviderToken { get; set; } = string.Empty;
        [Required][EmailAddress] public string Email    { get; set; } = string.Empty;
        [Required] public string FullName      { get; set; } = string.Empty;
    }

    public class RefreshDto
    {
        [Required(ErrorMessage = "Refresh token không được để trống")]
        public string RefreshToken { get; set; } = string.Empty;
    }

    public class ChangePasswordDto
    {
        [Required(ErrorMessage = "Mật khẩu cũ không được để trống")]
        public string OldPassword { get; set; } = string.Empty;

        [Required(ErrorMessage = "Mật khẩu mới không được để trống")]
        [MinLength(6, ErrorMessage = "Mật khẩu mới phải có ít nhất 6 ký tự")]
        public string NewPassword { get; set; } = string.Empty;
    }

    public class UpdateFcmTokenDto
    {
        [Required(ErrorMessage = "FCM token không được để trống")]
        public string FcmToken { get; set; } = string.Empty;

        public string? DeviceName { get; set; }
    }

    // ============================================================
    // User DTOs
    // ============================================================
    public class CreateUserDto
    {
        [Required(ErrorMessage = "Họ tên không được để trống")]
        [MaxLength(100, ErrorMessage = "Họ tên tối đa 100 ký tự")]
        public string FullName { get; set; } = string.Empty;

        [Required(ErrorMessage = "Email không được để trống")]
        [EmailAddress(ErrorMessage = "Email không đúng định dạng")]
        public string Email { get; set; } = string.Empty;

        [Required(ErrorMessage = "Mật khẩu không được để trống")]
        [MinLength(6, ErrorMessage = "Mật khẩu phải có ít nhất 6 ký tự")]
        public string Password { get; set; } = string.Empty;

        [Required(ErrorMessage = "Vai trò không được để trống")]
        public string Role { get; set; } = string.Empty;

        public string? ClassroomId { get; set; }
    }

    public class UpdateUserDto
    {
        [MaxLength(100)] public string? FullName { get; set; }

        [EmailAddress(ErrorMessage = "Email không đúng định dạng")]
        public string? Email { get; set; }

        [MinLength(6, ErrorMessage = "Mật khẩu phải có ít nhất 6 ký tự")]
        public string? Password { get; set; }

        public string? Role       { get; set; }
        public string? ClassroomId { get; set; }
    }

    // ============================================================
    // Area DTOs
    // ============================================================
    public class CreateAreaDto
    {
        [Required(ErrorMessage = "Tên khu vực không được để trống")]
        [MaxLength(100, ErrorMessage = "Tên khu vực tối đa 100 ký tự")]
        public string Name { get; set; } = string.Empty;

        [MaxLength(500)] public string? Description { get; set; }
    }

    public class UpdateAreaDto
    {
        [MaxLength(100)] public string? Name        { get; set; }
        [MaxLength(500)] public string? Description { get; set; }
    }

    // ============================================================
    // Device DTOs
    // ============================================================
    public class CreateDeviceDto
    {
        [MaxLength(100)] public string? Id { get; set; }

        [Required(ErrorMessage = "Tên thiết bị không được để trống")]
        [MaxLength(100)] public string Name { get; set; } = string.Empty;

        [Required(ErrorMessage = "Khu vực không được để trống")]
        public string AreaId { get; set; } = string.Empty;

        [Range(1, 100, ErrorMessage = "Tầng phải từ 1 đến 100")]
        public int Floor { get; set; }

        public double PositionX { get; set; }
        public double PositionY { get; set; }
    }

    public class UpdateDeviceDto
    {
        public string? NewId                   { get; set; }
        [MaxLength(100)] public string? Name   { get; set; }
        public string? AreaId                  { get; set; }
        [Range(1, 100)] public int? Floor      { get; set; }
        public double? PositionX               { get; set; }
        public double? PositionY               { get; set; }
        public string? Status                  { get; set; }
        [Range(0, 100)] public int? BatteryLevel { get; set; }
    }

    // ============================================================
    // Alert DTOs
    // ============================================================
    public class CreateAlertDto
    {
        [Required(ErrorMessage = "Device ID không được để trống")]
        public string DeviceId { get; set; } = string.Empty;

        [Required(ErrorMessage = "Loại âm thanh không được để trống")]
        public string SoundType { get; set; } = string.Empty;

        [Range(0.0, 100.0, ErrorMessage = "Độ tin cậy phải từ 0 đến 100")]
        public double ConfidenceScore { get; set; }

        public string? AudioFileUrl { get; set; }
    }

    public class UpdateAlertDto
    {
        public string? Status      { get; set; }
        [MaxLength(2000)] public string? Notes { get; set; }
        public bool? IsEvidence    { get; set; }
    }

    public class OfflineActionDto
    {
        [Required] public string AlertId { get; set; } = string.Empty;

        [Required] public string Action  { get; set; } = string.Empty; // "update_status" | "add_note"

        public string? Status { get; set; }
        [MaxLength(2000)] public string? Notes { get; set; }
        public double TimestampSeconds { get; set; }
    }

    public class AlertQueryDto
    {
        public string? DateFrom  { get; set; }
        public string? DateTo    { get; set; }
        public string? Area      { get; set; }
        public string? SoundType { get; set; }
        public string? Status    { get; set; }

        [Range(0, int.MaxValue)] public int Offset { get; set; } = 0;
        [Range(1, 1000, ErrorMessage = "Limit phải từ 1 đến 1000")] public int Limit { get; set; } = 20;
    }

    // ============================================================
    // Settings DTOs
    // ============================================================
    public class SettingItem
    {
        [Required] public string Key   { get; set; } = string.Empty;
        [Required] public string Value { get; set; } = string.Empty;
    }

    public class UpdateSettingsDto
    {
        [Required] public List<SettingItem> Settings { get; set; } = new();
    }
}
